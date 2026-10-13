"""Clarity API route handlers — /api (and /clarity/v1 alias)."""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "data"))

from flask import Blueprint, jsonify, request, send_file

from server.db.connection import connect, get_db_path
from server.db.repositories import Store
from server.gateway.middleware import customer_id
from server.services import calendar as calendar_svc
from server.services import funding as funding_svc
from server.services import clock as clock_svc
from server.services import connector as connector_svc
from server.services import extraction as extraction_svc
from server.services import issue as issue_svc
from server.services import notification as notification_svc
from server.services import review as review_svc
from server.services import rules as rules_svc
from server.services import validation as validation_svc
from server.services.review import AiCheckRequired
from domain.config import company_config, cycle_config, rules_config

bp = Blueprint("clarity", __name__)


def _store() -> Store:
    return Store(connect())


def _as_of() -> str:
    body = request.get_json(silent=True) or {}
    raw = request.args.get("asOf") or request.args.get("date") or body.get("asOf") or body.get("date")
    if not raw:
        stored = _store().meta("prototype_date")
        raw = stored
    resolved = calendar_svc.resolve_date(raw)
    clock_svc.set_as_of(resolved)
    return resolved


def _problem(status: int, title: str, detail: str, type_: str = "about:blank", **extra):
    body = {"type": type_, "title": title, "status": status, "detail": detail, **extra}
    return jsonify(body), status


@bp.get("/meta/prototype-dates")
@bp.get("/config")
def meta_prototype_dates():
    if request.path.endswith("/config"):
        return jsonify(
            {
                "cycle": cycle_config(),
                "rules": rules_config(),
                "company": company_config(),
                "dates": calendar_svc.prototype_dates(),
            }
        )
    return jsonify(calendar_svc.prototype_dates())


@bp.get("/state")
def state():
    as_of = _as_of()
    store = _store()
    cid = customer_id()
    return jsonify(
        {
            "asOf": as_of,
            "dates": calendar_svc.prototype_dates(),
            "overview": issue_svc.overview(store, cid, as_of),
            "issues": issue_svc.list_issues(store, cid, status="open", as_of=as_of),
            "employees": validation_svc.list_employees(store, cid, as_of)["employees"],
            "review": review_svc.get_review(store, cid, as_of),
            "notifications": notification_svc.list_notifications(store, cid, as_of),
            "config": {"cycle": cycle_config(), "rules": rules_config(), "company": company_config()},
        }
    )


@bp.get("/cycles/current")
def cycles_current():
    try:
        return jsonify(calendar_svc.cycle_view(_store(), customer_id(), _as_of()))
    except LookupError:
        return _problem(404, "Not Found", "Customer or cycle not found")


@bp.get("/cycles/current/overview")
def cycles_overview():
    try:
        return jsonify(issue_svc.overview(_store(), customer_id(), _as_of()))
    except LookupError:
        return _problem(404, "Not Found", "Customer or cycle not found")


@bp.get("/employees")
def employees_list():
    country = request.args.get("country")
    action = request.args.get("action_needed") or request.args.get("action")
    action_needed = None
    if action is not None and action not in ("", "all"):
        action_needed = action.lower() in ("1", "true", "yes")
    page = request.args.get("page", type=int)
    page_size = request.args.get("pageSize", type=int) or request.args.get("page_size", type=int)
    # Paginate only when page/pageSize are provided; boot/cache still loads the full list.
    store = _store()
    data = validation_svc.list_employees(
        store,
        customer_id(),
        _as_of(),
        country=country if country and country != "all" else None,
        action_needed=action_needed,
        q=request.args.get("q"),
        status=request.args.get("status"),
        filter_key=request.args.get("filter") or None,
        page=page,
        page_size=page_size,
    )
    return jsonify(data)


@bp.get("/employees/<employee_id>")
def employees_get(employee_id: str):
    try:
        return jsonify(validation_svc.get_employee_detail(_store(), employee_id, _as_of(), customer_id()))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found", issue_id=employee_id)


@bp.post("/employees")
def employees_create():
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        emp, created = connector_svc.create_employee(_store(), customer_id(), body, as_of=as_of)
        return jsonify(emp), (201 if created else 200)
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/inputs/preview")
def inputs_preview():
    """Dry-run cycle assignment + findings (no DB write)."""
    from server.services import inputs as inputs_svc

    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    kind = (body.get("kind") or "employee").lower()
    try:
        if kind in ("otp", "one_time", "one-time", "bonus"):
            emp = None
            eid = body.get("employeeId")
            if eid:
                emp = _store().get_employee(eid)
            return jsonify(inputs_svc.preview_one_time(body, as_of=as_of, employee=emp))
        if kind in ("pay_edit", "pay-edit", "salary"):
            eid = body.get("employeeId")
            if not eid:
                return _problem(400, "Bad Request", "employeeId required")
            return jsonify(inputs_svc.preview_pay_edit(_store(), eid, body, as_of=as_of))
        return jsonify(inputs_svc.preview_employee(body, as_of=as_of))
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))
    except LookupError as e:
        return _problem(404, "Not Found", str(e))


@bp.get("/documents/<doc_id>/file")
def document_file(doc_id: str):
    """Open a stored offer, bonus, or hike letter. Demo PDFs are served from disk."""
    store = _store()
    doc = store.get_document(doc_id)
    if not doc:
        return _problem(404, "Not Found", "Document not found")
    emp = store.get_employee(doc["employee_id"])
    if not emp or emp["customer_id"] != customer_id():
        return _problem(404, "Not Found", "Document not found")
    name = Path(doc.get("file_name") or "").name
    demo = ROOT / "demo_documents" / name
    if not demo.is_file():
        for alias, fixture in extraction_svc.DEMO_FILENAME_ALIASES.items():
            if name in (alias, fixture):
                candidate = ROOT / "demo_documents" / alias
                if candidate.is_file():
                    demo = candidate
                    break
    if demo.is_file():
        return send_file(demo, mimetype="application/pdf", as_attachment=False, download_name=name or demo.name)
    title = html.escape(name or "Letter")
    lines = "".join(
        f"<li>{html.escape(str(m.get('multiplierField') or ''))}: {html.escape(str(m.get('value') or ''))}</li>"
        for m in (doc.get("mappings") or [])
        if m.get("value")
    )
    page = (
        "<!doctype html><meta charset='utf-8'><title>"
        + title
        + "</title><body style='font-family:sans-serif;padding:24px'>"
        + f"<h1>{title}</h1><ul>{lines or '<li>No extracted fields</li>'}</ul></body>"
    )
    return page, 200, {"Content-Type": "text/html; charset=utf-8"}


@bp.post("/documents/generate")
def documents_generate():
    from server.services.documents_generate import generate_sample_pdf

    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(generate_sample_pdf(body))
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.patch("/employees/<employee_id>")
def employees_patch(employee_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        emp = review_svc.patch_employee(
            _store(),
            employee_id,
            body,
            as_of=as_of,
            customer_id=customer_id(),
            confirm_ai=bool(body.get("confirmAiCheck")),
        )
        return jsonify(emp)
    except AiCheckRequired as e:
        return _problem(
            409,
            "AI check",
            e.payload.get("message") or "This pay change needs an AI check.",
            type_="https://multiplier.example/errors/ai-check",
            aiCheck=e.payload,
        )
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/employees/<employee_id>/documents")
def employees_documents(employee_id: str):
    body = request.get_json(force=True, silent=True) or {}
    fixture = body.get("fixture") or body.get("filename") or body.get("fileName")
    as_of = _as_of()
    if not fixture:
        return _problem(400, "Bad Request", "fixture filename required")
    try:
        return jsonify(
            validation_svc.attach_document(
                _store(), employee_id, fixture, as_of=as_of, customer_id=customer_id()
            )
        )
    except LookupError as e:
        return _problem(404, "Not Found", str(e))
    except (PermissionError, ValueError) as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/employees/<employee_id>/missing-fields")
def employees_missing_fields(employee_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    fields = body.get("fields") or {k: v for k, v in body.items() if k not in ("asOf", "source", "fillSample")}
    if body.get("fillSample"):
        from server.services import rules as rules_svc

        missing = _store().missing_fields(employee_id, as_of)
        fields = rules_svc.demo_values(employee_id, missing)
    try:
        return jsonify(
            validation_svc.apply_missing_fields(
                _store(),
                employee_id,
                fields,
                as_of=as_of,
                source=body.get("source") or "Edited by HR admin",
            )
        )
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/employees/<employee_id>/one-time-payments")
def employees_otp(employee_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        return jsonify(connector_svc.add_one_time_payment(_store(), employee_id, body, as_of=as_of, customer_id=customer_id()))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except rules_svc.DuplicatePaymentWarning as e:
        return _problem(409, "Conflict", e.payload.get("message", "Possible duplicate payment"), details=e.payload)
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/employees/<employee_id>/exit")
def employees_exit(employee_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        return jsonify(connector_svc.record_exit(_store(), employee_id, body, as_of=as_of, customer_id=customer_id()))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.delete("/employees/<employee_id>/exit")
def employees_exit_undo(employee_id: str):
    as_of = _as_of()
    try:
        return jsonify(connector_svc.undo_exit(_store(), employee_id, as_of=as_of, customer_id=customer_id()))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.get("/issues")
def issues_list():
    status = request.args.get("status", "open")
    if status == "all":
        status = None
    try:
        return jsonify({"issues": issue_svc.list_issues(_store(), customer_id(), status=status, as_of=_as_of()), "asOf": _as_of()})
    except LookupError:
        return _problem(404, "Not Found", "Cycle not found")


@bp.get("/issues/<issue_id>")
def issues_get(issue_id: str):
    try:
        return jsonify(issue_svc.get_issue(_store(), issue_id, as_of=_as_of()))
    except LookupError:
        return _problem(404, "Not Found", "Issue not found", issue_id=issue_id)


@bp.post("/issues/<issue_id>/resolve")
def issues_resolve(issue_id: str):
    body = request.get_json(force=True, silent=True) or {}
    resolution = body.get("resolution") or "confirm"
    payload = body.get("payload")
    actor = body.get("actor") or "HR admin"
    as_of = _as_of()
    try:
        result = issue_svc.resolve(
            _store(),
            issue_id,
            resolution=resolution,
            payload=payload,
            actor=actor,
            as_of=as_of,
            customer_id=customer_id(),
        )
        return jsonify(result)
    except LookupError:
        return _problem(404, "Not Found", "Issue not found", issue_id=issue_id)
    except PermissionError as e:
        return _problem(
            501,
            "Not Implemented",
            "Not built in prototype",
            type_="https://multiplier.example/errors/not-built",
            code=str(e),
        )
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/issues/<issue_id>/remind")
def issues_remind(issue_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        return jsonify(
            issue_svc.remind(
                _store(),
                issue_id,
                as_of=as_of,
                customer_id=customer_id(),
                fields=body.get("fields"),
            )
        )
    except LookupError:
        return _problem(404, "Not Found", "Issue not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.get("/forms/<token>")
def forms_get(token: str):
    from server.services import forms as forms_svc

    try:
        return jsonify(forms_svc.get_form(_store(), token, as_of=_as_of(), customer_id=customer_id()))
    except LookupError:
        return _problem(404, "Not Found", "Form link is invalid")
    except PermissionError as e:
        code = str(e)
        if code == "token_used":
            return _problem(410, "Gone", "This form link has already been used")
        if code == "token_expired":
            return _problem(410, "Gone", "This form link expired after the Oct 15 cutoff")
        return _problem(410, "Gone", "Form link is no longer valid")


@bp.post("/forms/<token>")
def forms_post(token: str):
    from server.services import forms as forms_svc

    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    fields = body.get("fields") or {k: v for k, v in body.items() if k not in ("asOf",)}
    try:
        return jsonify(
            forms_svc.submit_form(
                _store(), token, fields, as_of=as_of, customer_id=customer_id()
            )
        )
    except LookupError:
        return _problem(404, "Not Found", "Form link is invalid")
    except PermissionError as e:
        code = str(e)
        if code == "token_used":
            return _problem(410, "Gone", "This form link has already been used")
        if code == "token_expired":
            return _problem(410, "Gone", "This form link expired after the Oct 15 cutoff")
        return _problem(410, "Gone", "Form link is no longer valid")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.get("/review")
def review_get():
    try:
        return jsonify(review_svc.get_review(_store(), customer_id(), _as_of()))
    except LookupError:
        return _problem(404, "Not Found", "Cycle not found")


@bp.post("/review/<line_id>/llm-decide")
def review_llm_decide(line_id: str):
    """Re-run LLM approve/hold judgment for one review line."""
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        review = review_svc.get_review(_store(), customer_id(), as_of)
        line = next((l for l in review.get("lines") or [] if l.get("id") == line_id), None)
        if not line:
            return _problem(404, "Not Found", "Review line not found")
        from server.services import llm as llm_svc

        decision = llm_svc.decide_review_line(line, force=True)
        line["llmDecision"] = decision
        return jsonify({"lineId": line_id, "llmDecision": decision, "line": line})
    except LookupError:
        return _problem(404, "Not Found", "Cycle not found")


@bp.post("/review/approve")
@bp.post("/review/<line_id>/approve")
def review_approve(line_id: Optional[str] = None):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    line_id = line_id or body.get("lineId")
    if not line_id:
        return _problem(400, "Bad Request", "lineId required — per-line approve only")
    try:
        return jsonify(review_svc.approve_line(_store(), customer_id(), line_id, as_of))
    except LookupError:
        return _problem(404, "Not Found", "Review line not found — it may not belong to this cycle")


@bp.post("/review/<line_id>/reject")
def review_reject(line_id: str):
    as_of = _as_of()
    try:
        return jsonify(review_svc.reject_line(_store(), customer_id(), line_id, as_of))
    except LookupError:
        return _problem(404, "Not Found", "Review line not found")
    except PermissionError as e:
        return _problem(409, "Conflict", str(e))


@bp.post("/review/<line_id>/unapprove")
def review_unapprove(line_id: str):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        return jsonify(review_svc.unapprove_line(_store(), customer_id(), line_id, as_of))
    except LookupError:
        return _problem(404, "Not Found", "Review line not found")
    except PermissionError as e:
        return _problem(409, "Conflict", str(e))


@bp.post("/review/signoff")
def review_signoff():
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    try:
        return jsonify(review_svc.signoff(_store(), customer_id(), as_of, actor=body.get("actor") or "HR admin"))
    except PermissionError as e:
        return _problem(409, "Conflict", str(e), type_="https://multiplier.example/errors/signoff-blocked")
    except LookupError:
        return _problem(404, "Not Found", "Cycle not found")


@bp.post("/review/reopen")
@bp.post("/employees/<employee_id>/reopen-review")
def review_reopen(employee_id: Optional[str] = None):
    body = request.get_json(force=True, silent=True) or {}
    as_of = _as_of()
    eid = employee_id or body.get("employeeId")
    if not eid:
        return _problem(400, "Bad Request", "employeeId required")
    try:
        return jsonify(review_svc.reopen_matched(_store(), customer_id(), eid, as_of))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.post("/funding/decision")
def funding_decision():
    body = request.get_json(silent=True) or {}
    decision = str(body.get("decision") or "").strip().lower()
    cycle_key = body.get("cycleKey") or body.get("cycle_key")
    try:
        view = funding_svc.record_funding_decision(
            _store(), customer_id(), _as_of(), decision, str(cycle_key) if cycle_key else None
        )
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))
    return jsonify(view)


@bp.get("/notifications")
def notifications_list():
    channel = request.args.get("channel", "email")
    try:
        return jsonify(
            {
                "notifications": notification_svc.list_notifications(_store(), customer_id(), _as_of(), channel=channel),
                "asOf": _as_of(),
            }
        )
    except LookupError:
        return _problem(404, "Not Found", "Cycle not found")


@bp.post("/notifications/query")
def notifications_query():
    body = request.get_json(silent=True) or {}
    as_of = _as_of()
    store = _store()
    cycle = store.get_current_cycle(customer_id())
    if not cycle:
        return _problem(404, "Not Found", "Cycle not found")
    recipient = str(body.get("recipient") or "").strip()
    message = str(body.get("body") or "").strip()
    if not recipient or not message:
        return _problem(400, "Bad Request", "Recipient and message are required")
    store.add_notification(
        cycle["id"],
        send_date=as_of[:10],
        recipient=recipient,
        subject=str(body.get("subject") or "Payroll query"),
        body_summary=message,
        actions=[],
        cta_label="Open Action needed",
        cta_href=str(body.get("href") or "/payroll/actions"),
        kind="hr_query",
    )
    return jsonify({"ok": True})


@bp.get("/notifications/<notification_id>")
def notifications_get(notification_id: str):
    try:
        return jsonify(notification_svc.get_notification(_store(), notification_id, customer_id(), _as_of()))
    except LookupError:
        return _problem(404, "Not Found", "Notification not found")


@bp.get("/documents/fixtures")
def documents_fixtures():
    return jsonify({"fixtures": validation_svc.list_document_fixtures(_store())})


@bp.post("/drive/extract")
@bp.post("/documents/extract")
def drive_extract():
    body = request.get_json(force=True, silent=True) or {}
    as_of = calendar_svc.resolve_date(
        request.form.get("asOf")
        or body.get("asOf")
        or body.get("date")
        or _as_of()
    )
    file_name = (
        body.get("fileName")
        or body.get("filename")
        or request.form.get("fileName")
        or request.form.get("filename")
    )
    employee_id = body.get("employeeId") or request.form.get("employeeId")
    uploaded = request.files.get("file")
    upload_bytes = None
    if uploaded and uploaded.filename:
        file_name = uploaded.filename
        upload_bytes = uploaded.read()
    try:
        result = extraction_svc.extract(
            _store(),
            customer_id=customer_id(),
            as_of=as_of,
            file_name=file_name,
            file_id=body.get("fileId"),
            access_token=body.get("accessToken"),
            employee_id=employee_id,
            upload_bytes=upload_bytes,
        )
        if employee_id:
            result["employee"] = validation_svc.get_employee_detail(
                _store(), employee_id, as_of, customer_id()
            )
        return jsonify(result)
    except LookupError as e:
        return _problem(404, "Not Found", str(e))
    except PermissionError as e:
        return _problem(400, "Bad Request", str(e), code="drive_access")
    except ValueError as e:
        return _problem(400, "Bad Request", str(e))


@bp.get("/sync")
def sync_status():
    from server.services import sync as sync_svc

    as_of = _as_of()
    return jsonify(sync_svc.status(_store(), customer_id(), as_of))


@bp.post("/sync")
def sync_run():
    from server.services.sync import SyncFailed, SyncLimitError, run_sync

    body = request.get_json(silent=True) or {}
    as_of = _as_of()
    trigger = body.get("trigger") or "Manual"
    try:
        result = run_sync(_store(), customer_id(), as_of, trigger=trigger)
        return jsonify(result)
    except SyncLimitError as e:
        return _problem(429, "Sync limit", str(e))
    except SyncFailed as e:
        return _problem(409, "Sync failed", str(e))


@bp.post("/sync/refresh/<employee_id>")
def sync_refresh(employee_id: str):
    from server.services.sync import refresh_employee

    as_of = _as_of()
    try:
        return jsonify(refresh_employee(_store(), customer_id(), employee_id, as_of))
    except LookupError:
        return _problem(404, "Not Found", "Employee not found")


@bp.post("/demo/reset")
def demo_reset():
    from data.seed_db import seed_database

    path = get_db_path()
    seed_database(Path(path), 42, quiet=True)
    return jsonify({"ok": True, "asOf": cycle_config()["defaultPrototypeDate"]})


@bp.get("/demo/date")
@bp.put("/demo/date")
def demo_date():
    store = _store()
    if request.method == "PUT":
        body = request.get_json(force=True, silent=True) or {}
        value = calendar_svc.resolve_date(body.get("date") or body.get("asOf"))
        store.set_meta("prototype_date", value)
        return jsonify({"asOf": value})
    return jsonify({"asOf": store.meta("prototype_date") or cycle_config()["defaultPrototypeDate"]})
