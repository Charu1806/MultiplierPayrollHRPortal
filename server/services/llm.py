"""LLM helpers — document field mapping + review approve/hold decisions.

Does not set pay timing, cutoffs, or cycle routing (those stay in calendar/rules).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

SCHEMA_HINT = {
    "employeeName": "string|null",
    "jobTitle": "string|null",
    "startDate": "YYYY-MM-DD|null",
    "annualSalary": "number|null",
    "currency": "string|null",
    "documentType": "offer|bonus|other|null",
    "oneTimePaymentAmount": "number|null",
    "oneTimePaymentType": "Bonus|Reimbursement|Arrears|Other|null",
    "pan": "string|null",
    "taxId": "string|null",
    "bankAccount": "string|null",
    "confidence": "object of field→0..1",
}

# In-process cache so Review refresh does not re-bill the model every click.
_decision_cache: Dict[str, Dict[str, Any]] = {}


def llm_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _provider() -> str:
    """openai | anthropic — from LLM_PROVIDER, or inferred from model / base URL."""
    explicit = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("openai", "anthropic"):
        return explicit
    model = (os.environ.get("LLM_MODEL") or "").lower()
    base = (os.environ.get("LLM_BASE_URL") or "").lower()
    if "anthropic" in base or "claude" in model or "opus" in model or "sonnet" in model:
        return "anthropic"
    return "openai"


def _parse_json_content(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop opening ```json / ``` and closing ```
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _chat_json(system: str, user: str, *, timeout: int = 12) -> Dict[str, Any]:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY not set")
    provider = _provider()
    if provider == "anthropic":
        return _chat_json_anthropic(key, system, user, timeout=timeout)
    return _chat_json_openai(key, system, user, timeout=timeout)


def _chat_json_openai(key: str, system: str, user: str, *, timeout: int) -> Dict[str, Any]:
    model = os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    base = (os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    body = json.dumps(
        {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user[:14000]},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")[:400]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    content = payload["choices"][0]["message"]["content"]
    return _parse_json_content(content)


def _chat_json_anthropic(key: str, system: str, user: str, *, timeout: int) -> Dict[str, Any]:
    model = os.environ.get("LLM_MODEL") or "claude-opus-4-5"
    base = (os.environ.get("LLM_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    # Accept either https://api.anthropic.com or .../v1
    if base.endswith("/v1"):
        url = f"{base}/messages"
    else:
        url = f"{base}/v1/messages"
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 1024,
            "system": system + "\n\nRespond with a single JSON object only — no markdown.",
            "messages": [{"role": "user", "content": user[:14000]}],
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(timeout, 45)) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")[:400]
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {detail}") from exc
    blocks = payload.get("content") or []
    parts: List[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, str):
            parts.append(block)
    return _parse_json_content("\n".join(parts))


def download_drive_bytes(file_id: str, access_token: str) -> bytes:
    """Download a Drive file. The token is used once and never stored."""
    if not access_token:
        raise PermissionError("Couldn't open this file – check you have access")
    headers = {"Authorization": f"Bearer {access_token}"}

    def _get(url: str) -> bytes:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    media = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    try:
        return _get(media)
    except urllib.error.HTTPError as exc:
        # Native Google Docs are not downloadable as media; export them as PDF.
        if exc.code not in (400, 403):
            raise PermissionError("Couldn't open this file – check you have access") from exc
        export = (
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
            "?mimeType=application/pdf"
        )
        try:
            return _get(export)
        except urllib.error.HTTPError as export_exc:
            raise PermissionError("Couldn't open this file – check you have access") from export_exc


def download_drive_text(file_id: str, access_token: str, filename: str = "") -> str:
    """Download file bytes from Drive; caller must not persist the token."""
    from server.services.extraction import text_from_bytes

    return text_from_bytes(download_drive_bytes(file_id, access_token), filename)


def map_document(text: str) -> Dict[str, Any]:
    data = _chat_json(
        "Extract payroll fields from the document. Return JSON only matching this schema: "
        + json.dumps(SCHEMA_HINT)
        + ". Use null when not found. Include a confidence 0-1 per field.",
        text,
        timeout=45 if _provider() == "anthropic" else 12,
    )
    return _validate(data)


def decide_review_line(line: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    """LLM decides whether HR should approve this review line."""
    cache_key = "|".join(
        [
            str(line.get("id") or ""),
            str(line.get("changeSummary") or ""),
            str(line.get("matchingSource") or ""),
            str(line.get("whyFlagged") or ""),
        ]
    )
    if not force and cache_key in _decision_cache:
        return _decision_cache[cache_key]

    if not llm_configured():
        decision = _fallback_review_decision(line)
        _decision_cache[cache_key] = decision
        return decision

    system = (
        "You are a payroll review assistant for Multiplier. "
        "Decide whether HR should APPROVE this pay change for the current cycle, or HOLD it. "
        "Judge from evidence: supporting document, matching source, whether the change looks like a "
        "legitimate bonus/arrears/raise vs an unexplained spike or missing documentation. "
        "Do NOT invent documents that are not listed. "
        "Return JSON only: "
        '{"recommend":"approve"|"hold","confidence":0..1,"reason":"short HR-facing sentence",'
        '"label":"optional short chip label"}'
    )
    user = json.dumps(
        {
            "employeeName": line.get("employeeName"),
            "country": line.get("country"),
            "changeSummary": line.get("changeSummary"),
            "whyFlagged": line.get("whyFlagged"),
            "matchingSource": line.get("matchingSource"),
            "origin": line.get("origin"),
            "requiresEmployeeNotified": bool(line.get("requiresEmployeeNotified")),
        }
    )
    try:
        raw = _chat_json(system, user, timeout=45 if _provider() == "anthropic" else 12)
        recommend = str(raw.get("recommend") or "hold").strip().lower()
        if recommend not in ("approve", "hold"):
            recommend = "hold"
        conf = raw.get("confidence")
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))
        decision = {
            "recommend": recommend,
            "confidence": confidence,
            "reason": str(raw.get("reason") or "LLM reviewed this line.").strip(),
            "label": str(raw.get("label") or ("Approve" if recommend == "approve" else "Hold")).strip(),
            "source": "llm",
            "provider": _provider(),
            "model": os.environ.get("LLM_MODEL") or "",
        }
    except Exception as exc:  # noqa: BLE001
        decision = _fallback_review_decision(line, error=str(exc))

    _decision_cache[cache_key] = decision
    return decision


def classify_sync_change(kind: str, summary: str) -> Dict[str, Any]:
    """Decide whether a synced change is Action needed, Review, or already matched.

    The model chooses the queue. It does not approve the change. Without a configured
    model, pay changes go to Review and everything else is matched. Missing fields stay
    on Action needed through the existing validation rules.
    """
    if not llm_configured():
        if kind in ("hike", "bonus", "added", "leave", "exited"):
            return {
                "queue": "review",
                "reason": "Pay change needs a person to review it.",
                "source": "rules",
            }
        return {"queue": "matched", "reason": "No pay exception on this change.", "source": "rules"}

    system = (
        "You route one payroll sync change into a queue. "
        "Return JSON only: {\"queue\":\"action\"|\"review\"|\"matched\",\"reason\":\"short sentence\"}. "
        "Use action only for missing or invalid required data. "
        "Use review for a new employee, bonus, hike, leave, or exit that a person must authorise. "
        "Use matched when nothing is missing and no authorisation is required. "
        "Do not approve the change."
    )
    try:
        raw = _chat_json(system, json.dumps({"kind": kind, "summary": summary}), timeout=20)
        queue = str(raw.get("queue") or "review").strip().lower()
        if queue not in ("action", "review", "matched"):
            queue = "review"
        return {
            "queue": queue,
            "reason": str(raw.get("reason") or "Classified during sync.").strip(),
            "source": "llm",
        }
    except Exception:
        if kind in ("hike", "bonus", "added", "leave", "exited"):
            return {"queue": "review", "reason": "Pay change needs a person to review it.", "source": "rules"}
        return {"queue": "matched", "reason": "No pay exception on this change.", "source": "rules"}


def decide_pay_edit(
    *,
    employee_name: str,
    country: str,
    currency: str,
    september_pay: float,
    new_base: float,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """LLM decides whether a salary edit needs a second confirmation (hold) or is fine."""
    ctx = context or {}
    if not llm_configured():
        return {
            "needsConfirm": True,
            "label": "AI check",
            "message": (
                "LLM_API_KEY is not set — cannot judge this pay edit. "
                "Confirm carefully, or add LLM_API_KEY in .env."
            ),
            "source": "unavailable",
            "recommend": "hold",
            "confidence": 0.0,
            "direction": "up" if new_base > september_pay else "down",
            "multiple": _multiple_label(september_pay, new_base),
        }

    system = (
        "You are a payroll risk assistant. An HR admin is editing an employee's base salary. "
        "Decide if this edit should require a second confirmation before save. "
        "Approve (needsConfirm=false) when the change looks intentional and explained "
        "(raise, correction, documented). Hold (needsConfirm=true) when it looks like a "
        "mistyped one-off bonus, unexplained spike/drop, or missing context. "
        "Return JSON only: "
        '{"needsConfirm":true|false,"recommend":"approve"|"hold","confidence":0..1,'
        '"message":"HR-facing explanation","label":"AI check"}'
    )
    user = json.dumps(
        {
            "employeeName": employee_name,
            "country": country,
            "currency": currency,
            "septemberPay": september_pay,
            "newBase": new_base,
            "ratio": (new_base / september_pay) if september_pay else None,
            "notes": ctx,
        }
    )
    try:
        raw = _chat_json(system, user, timeout=45 if _provider() == "anthropic" else 12)
        needs = bool(raw.get("needsConfirm"))
        recommend = str(raw.get("recommend") or ("hold" if needs else "approve")).lower()
        if recommend not in ("approve", "hold"):
            recommend = "hold" if needs else "approve"
        return {
            "needsConfirm": needs or recommend == "hold",
            "label": str(raw.get("label") or "AI check"),
            "message": str(raw.get("message") or "Please confirm this pay change."),
            "source": "llm",
            "provider": _provider(),
            "model": os.environ.get("LLM_MODEL") or "",
            "recommend": recommend,
            "confidence": float(raw.get("confidence") or 0.7),
            "direction": "up" if new_base > september_pay else "down",
            "multiple": _multiple_label(september_pay, new_base),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "needsConfirm": True,
            "label": "AI check",
            "message": f"Could not reach the LLM ({exc}). Confirm this pay change manually.",
            "source": "error",
            "recommend": "hold",
            "confidence": 0.0,
            "direction": "up" if new_base > september_pay else "down",
            "multiple": _multiple_label(september_pay, new_base),
        }


def _multiple_label(september: float, new_base: float) -> str:
    if not september:
        return "n/a"
    ratio = new_base / september
    if ratio >= 1:
        return f"{ratio:.1f}×"
    return f"{ratio:.0%}"


def _fallback_review_decision(line: Dict[str, Any], *, error: Optional[str] = None) -> Dict[str, Any]:
    """Used only when LLM is missing/unreachable — not the old fixed % rules."""
    source = str(line.get("matchingSource") or "")
    has_doc = bool(source) and "no supporting" not in source.lower() and source != "—"
    if has_doc:
        recommend = "approve"
        reason = (
            "No LLM key — leaning Approve because a matching source/document is listed. "
            "Set LLM_API_KEY for a model decision."
        )
    else:
        recommend = "hold"
        reason = (
            "No LLM key — Hold until a supporting document or explanation is attached. "
            "Set LLM_API_KEY for a model decision."
        )
    if error:
        reason = f"LLM unavailable ({error}). {reason}"
    return {
        "recommend": recommend,
        "confidence": 0.35,
        "reason": reason,
        "label": "Approve?" if recommend == "approve" else "Hold",
        "source": "fallback",
    }


_payment_cache: Dict[str, List[str]] = {}


def payment_required_fields(country: str, fields: List[str]) -> List[str]:
    """Which of `fields` are required to pay someone in `country`.

    Owner (HR or employee) is irrelevant. The model decides. Tests and a missing
    key use the offline fallback so payroll still loads.
    """
    ordered = [f for f in fields if f]
    if not ordered:
        return []
    key = f"{country}|{'|'.join(sorted(ordered))}"
    if key in _payment_cache:
        return list(_payment_cache[key])

    fallback = _fallback_payment_fields(country, ordered)
    if os.environ.get("PYTEST_CURRENT_TEST") or not llm_configured():
        _payment_cache[key] = fallback
        return list(fallback)

    system = (
        "You decide which fields are required to pay an employee. "
        "A field is required only if payroll cannot legally or practically pay them without it "
        "(tax identifier, bank details used to send money, salary, start date). "
        "HR-record fields that are not needed to run pay, such as the manager's name, are not required. "
        "Whether HR or the employee owns the field does not matter. "
        "Return JSON only: {\"paymentRequired\": [names copied from the input list]}. "
        "Do not add names that were not in the input."
    )
    user = json.dumps({"country": country, "fields": ordered})
    try:
        raw = _chat_json(system, user, timeout=25)
        chosen = raw.get("paymentRequired")
        if not isinstance(chosen, list):
            result = fallback
        else:
            allowed = set(ordered)
            result = [f for f in ordered if f in allowed and f in {str(c) for c in chosen}]
    except Exception:  # noqa: BLE001 — pay timing must still load
        result = fallback
    _payment_cache[key] = result
    return list(result)


def _fallback_payment_fields(country: str, fields: List[str]) -> List[str]:
    """Offline stand-in: country payment fields from rules, plus salary and start date. Not Manager."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    data = str(root / "data")
    if data not in sys.path:
        sys.path.insert(0, data)
    from domain.config import rules_config

    rules = rules_config()
    listed = set((rules.get("requiredFields") or {}).get(country) or [])
    listed.update({"Start date", "Salary"})
    return [f for f in fields if f in listed]


_explain_cache: Dict[str, str] = {}


def explain_hire_pay(facts: Dict[str, Any]) -> str:
    """HR-facing explanation. Amounts and the pay month are already decided; the model only writes the sentence."""
    cache_key = json.dumps(facts, sort_keys=True, default=str)
    if cache_key in _explain_cache:
        return _explain_cache[cache_key]

    fallback = _fallback_hire_explanation(facts)
    # Tests stay offline. The running app calls the model.
    if os.environ.get("PYTEST_CURRENT_TEST") or not llm_configured():
        _explain_cache[cache_key] = fallback
        return fallback

    system = (
        "You explain a new hire's pay placement to an HR admin. "
        "The payroll engine already decided the amounts, the prorated days, and which payroll run pays them. "
        "Do not change any amount, date, or pay month. "
        "If a month is prorated, say that month's salary is prorated and include the day count and the prorated amount. "
        "Say which payroll run pays it, and that the base monthly net is unchanged. "
        "Two short sentences. No markdown. "
        'Return JSON only: {"explanation":"..."}'
    )
    try:
        raw = _chat_json(system, json.dumps(facts), timeout=25)
        text = str(raw.get("explanation") or "").strip()
        if not text or "prorat" not in text.lower():
            text = fallback
    except Exception:  # noqa: BLE001 — profile still loads if the model is down
        text = fallback
    _explain_cache[cache_key] = text
    return text


def _fallback_hire_explanation(facts: Dict[str, Any]) -> str:
    hired = facts.get("hired") or "this month"
    added = facts.get("added")
    paid_in = facts.get("paidIn") or "the next payroll"
    head = f"Hired {hired}"
    if added:
        head += f" and added {added}"
    head += f", so this is paid in {paid_in}."
    bits = []
    for row in facts.get("proratedMonths") or []:
        month = row.get("month") or "That month"
        days = f"{row.get('daysWorked')}/{row.get('daysInMonth')} days"
        amount = row.get("amount") or ""
        bits.append(f"{month} salary is prorated ({days}{', ' + amount if amount else ''})")
    body = " ".join(bits)
    net = facts.get("monthlyNet")
    tail = f" Base monthly net remains {net}." if net else ""
    return f"{head} {body}.{tail}".replace("..", ".")


def _validate(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "employeeName": data.get("employeeName"),
        "jobTitle": data.get("jobTitle"),
        "startDate": data.get("startDate"),
        "annualSalary": data.get("annualSalary"),
        "currency": data.get("currency"),
        "documentType": data.get("documentType"),
        "oneTimePaymentAmount": data.get("oneTimePaymentAmount"),
        "oneTimePaymentType": data.get("oneTimePaymentType"),
        "pan": data.get("pan"),
        "taxId": data.get("taxId"),
        "bankAccount": data.get("bankAccount"),
        "confidence": data.get("confidence") or {},
    }
    return out


def extracted_to_mappings(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    conf = extracted.get("confidence") or {}

    def conf_label(key: str) -> str:
        c = conf.get(key, "high")
        if isinstance(c, (int, float)):
            return f"{int(c * 100)}%" if c <= 1 else f"{int(c)}%"
        s = str(c).strip().lower()
        if s in ("high", "medium", "low"):
            return s.capitalize()
        try:
            n = float(s)
            return f"{int(n * 100)}%" if n <= 1 else f"{int(n)}%"
        except ValueError:
            return str(c)

    def row(field: str, key: str, required: bool = False) -> Dict[str, Any]:
        val = extracted.get(key)
        ok = val not in (None, "", "null")
        return {
            "sourceSystem": "Document",
            "sourceField": field,
            "multiplierField": field,
            "value": str(val) if ok else "Not found",
            "status": "mapped" if ok else "missing",
            "confidence": conf_label(key) if ok else ("Required" if required else None),
        }

    rows = [
        row("Employee name", "employeeName"),
        row("Job title", "jobTitle"),
        row("Start date", "startDate"),
        row("Annual gross salary", "annualSalary", required=True),
        row("One-off bonus", "oneTimePaymentAmount"),
        row("PAN", "pan"),
        row("Tax ID", "taxId"),
        row("Bank account", "bankAccount"),
    ]
    return rows
