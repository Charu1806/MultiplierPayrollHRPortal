"""Signed single-use employee form tokens (expires after cycle cutoff)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from itsdangerous import BadSignature, URLSafeSerializer

from domain.calendar_rules import CUTOFF, parse_date, short_date
from server.db.repositories import Store, now_iso
from server.services.env_config import env


def _secret() -> str:
    return env("FORM_TOKEN_SECRET") or env("SMTP_PASS") or "payroll-clarity-dev-secret"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(_secret(), salt="payroll-form-v1")


_TOKEN_PREFIX = "f-"


def create_form_token(
    store: Store,
    *,
    employee_id: str,
    issue_id: Optional[str],
    as_of: str,
) -> str:
    jti = uuid.uuid4().hex
    expires_on = CUTOFF.isoformat()
    store.create_form_token(
        jti=jti,
        employee_id=employee_id,
        issue_id=issue_id,
        created_on=as_of,
        expires_on=expires_on,
    )
    raw = _serializer().dumps({"jti": jti, "employeeId": employee_id, "issueId": issue_id})
    # Prefix so the path never starts with "." (itsdangerous zlib marker).
    return f"{_TOKEN_PREFIX}{raw}"


def resolve_token(store: Store, token: str, *, as_of: Optional[str] = None) -> Dict[str, Any]:
    raw = token[len(_TOKEN_PREFIX) :] if token.startswith(_TOKEN_PREFIX) else token
    try:
        payload = _serializer().loads(raw)
    except BadSignature as exc:
        raise LookupError("invalid_token") from exc

    jti = payload.get("jti")
    employee_id = payload.get("employeeId")
    if not jti or not employee_id:
        raise LookupError("invalid_token")

    row = store.get_form_token(jti)
    if not row or row["employee_id"] != employee_id:
        raise LookupError("invalid_token")
    if row.get("used_at"):
        raise PermissionError("token_used")

    check_date = as_of or store.meta("prototype_date") or CUTOFF.isoformat()
    if parse_date(check_date) > parse_date(row["expires_on"]):
        raise PermissionError("token_expired")

    return {
        "jti": jti,
        "employeeId": employee_id,
        "issueId": row.get("issue_id") or payload.get("issueId"),
        "expiresOn": row["expires_on"],
        "cutoffLabel": short_date(row["expires_on"]),
    }


def mark_used(store: Store, jti: str) -> None:
    store.mark_form_token_used(jti, used_at=now_iso())
