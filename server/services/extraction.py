"""Document extraction — Drive download + text, with demo fallback on known filenames."""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.config import rules_config  # noqa: E402
from domain.calendar_rules import CUTOFF, parse_date, review_window_state  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import llm as llm_svc  # noqa: E402
from server.services import rules as rules_svc  # noqa: E402

TIMEOUT = int(rules_config().get("extractionTimeoutSeconds") or 8)
DEMO_FALLBACK = os.environ.get("DEMO_FALLBACK", "true").lower() in ("1", "true", "yes")

# demo_documents/ download names → seed fixture filenames (content-compatible)
DEMO_FILENAME_ALIASES = {
    "bonus_letter_james_patel_oct.pdf": "bonus_letter_james.pdf",
    "travel_reimbursement_chloe_oct.pdf": "travel_reimbursement_chloe.pdf",
    "offer_letter_priya_nair_oct.pdf": "offer_letter_priya.pdf",
    "offer_letter_arjun_mehta_oct.pdf": "offer_letter_arjun.pdf",
}


def resolve_fixture_filename(filename: str) -> str:
    base = (filename or "").split("/")[-1].strip()
    return DEMO_FILENAME_ALIASES.get(base, base)


def parse_document_text(text: str) -> Dict[str, Any]:
    """Generic rule-based extraction — never keyed by filename."""
    out: Dict[str, Any] = {"documentType": None, "confidence": {}}
    if not text:
        return out
    # Some generators use a placeholder glyph instead of ₹
    text = text.replace("■", "₹").replace("�", "₹")
    lower = text.lower()
    # A hike letter can also mention a bonus. Classify that before a plain bonus letter,
    # otherwise the whole increase is treated as a one-off and the new base is discarded.
    if any(
        phrase in lower
        for phrase in ("salary revision", "salary hike", "revised salary", "pay revision")
    ):
        out["documentType"] = "salary_revision"
    elif "bonus" in lower or "one-off" in lower or "one off" in lower or "spot bonus" in lower:
        out["documentType"] = "bonus"
    elif "reimburs" in lower or "expense" in lower:
        out["documentType"] = "reimbursement"
    elif "exit" in lower or "termination" in lower or "last working" in lower:
        out["documentType"] = "exit"
    elif "offer" in lower or "appointment" in lower or "joining" in lower:
        out["documentType"] = "offer"

    name_m = re.search(
        r"(?:employee|candidate|^name)\s*[:\-]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        text,
        re.I | re.M,
    )
    if name_m and "\n" in name_m.group(1):
        name_m = None
    if not name_m:
        name_m = re.search(
            r"(?:employee|candidate)\s*[:\-]\s*([A-Za-z][A-Za-z' \-]+?)(?:\n|$)",
            text,
            re.I,
        )
    if name_m:
        out["employeeName"] = name_m.group(1).strip()
        out["confidence"]["employeeName"] = "medium"

    role_m = re.search(r"(?:role|job title|designation)\s*[:\-]\s*([^\n]+)", text, re.I)
    if role_m:
        out["jobTitle"] = role_m.group(1).strip()
        out["confidence"]["jobTitle"] = "medium"

    # Prefer labeled amounts from demo letters
    otp_m = re.search(
        r"(?:one-off\s+bonus|spot\s+bonus|bonus\s+amount)\s*[:\-]\s*(?:£|₹|€|R\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.I,
    )
    annual_m = re.search(
        r"annual\s+gross\s+salary\s*[:\-]\s*(?:£|₹|€|R\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.I,
    )
    monthly_m = re.search(
        r"(?:new\s+)?monthly\s+base\s*[:\-]\s*(?:£|₹|€|R\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.I,
    )
    new_monthly_m = re.search(
        r"new\s+monthly\s+base\s*[:\-]\s*(?:£|₹|€|R\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.I,
    )
    increase_m = re.search(
        r"increase\s*[:\-]\s*(?:£|₹|€|R\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        re.I,
    )

    def _num(m: Optional[re.Match[str]]) -> Optional[float]:
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    if out["documentType"] == "salary_revision":
        annual = _num(annual_m)
        monthly = _num(new_monthly_m) or _num(monthly_m)
        bonus = _num(otp_m)
        if monthly is not None:
            out["monthlyBase"] = monthly
        if annual is not None:
            out["annualSalary"] = annual
        elif monthly is not None:
            out["annualSalary"] = monthly * 12
        if bonus is not None:
            out["oneTimePaymentAmount"] = bonus
            out["oneTimePaymentType"] = "Bonus"
        if out.get("annualSalary") is not None or bonus is not None:
            out["confidence"]["annualSalary"] = "medium"
            out["confidence"]["oneTimePaymentAmount"] = "medium"
            out["confidence"]["amount"] = "medium"
    elif out["documentType"] in ("bonus", "reimbursement"):
        amount = _num(otp_m) or _num(increase_m)
        if amount is None:
            amt_m = re.search(r"(?:£|₹|€|R\$)\s*([\d,]+(?:\.\d{1,2})?)", text)
            if not amt_m:
                amt_m = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:GBP|INR|EUR|BRL)", text, re.I)
            amount = _num(amt_m)
        if amount is not None:
            out["oneTimePaymentAmount"] = amount
            out["oneTimePaymentType"] = "Bonus" if out["documentType"] == "bonus" else "Reimbursement"
            out["confidence"]["oneTimePaymentAmount"] = "medium"
            out["confidence"]["amount"] = "medium"
    else:
        annual = _num(annual_m)
        monthly = _num(monthly_m)
        if annual is not None:
            out["annualSalary"] = annual
            out["confidence"]["annualSalary"] = "medium"
            out["confidence"]["amount"] = "medium"
        elif monthly is not None:
            out["annualSalary"] = monthly * 12
            out["confidence"]["annualSalary"] = "medium"
            out["confidence"]["amount"] = "medium"
        else:
            amt_m = re.search(r"(?:£|₹|€|R\$)\s*([\d,]+(?:\.\d{1,2})?)", text)
            if not amt_m:
                amt_m = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:GBP|INR|EUR|BRL)", text, re.I)
            amount = _num(amt_m)
            if amount is not None:
                out["annualSalary"] = amount if amount > 10000 else amount * 12
                out["confidence"]["annualSalary"] = "medium"
                out["confidence"]["amount"] = "medium"

    date_m = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if not date_m:
        date_m = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})",
            text,
            re.I,
        )
    if date_m:
        out["startDate"] = date_m.group(1)
        out["confidence"]["startDate"] = "low"

    for label, key, pattern in (
        ("PAN", "pan", r"\b([A-Z]{5}[0-9]{4}[A-Z])\b"),
        ("CPF", "cpf", r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b"),
        ("NI number", "niNumber", r"\b([A-Z]{2}\s?\d{6}\s?[A-Z])\b"),
        ("Tax ID", "taxId", r"\b(\d{11})\b"),
        ("Bank account", "bankAccount", r"(?:bank\s+account)\s*[:\-]\s*([A-Z0-9\- ]{6,})"),
    ):
        m = re.search(pattern, text, re.I)
        if m:
            out[key] = m.group(1).strip()
            out["confidence"][key] = "low"

    return out


def text_from_bytes(data: bytes, filename: str = "") -> str:
    """PDF, Word, or plain text. Used for uploads and Drive downloads."""
    name = (filename or "").lower()
    if data[:5] == b"%PDF" or name.endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if text.strip():
                return text
        except Exception:  # noqa: BLE001
            pass
    if name.endswith(".docx") or data[:2] == b"PK":
        try:
            import xml.etree.ElementTree as ET
            import zipfile
            from io import BytesIO

            with zipfile.ZipFile(BytesIO(data)) as archive:
                xml = archive.read("word/document.xml")
            root = ET.fromstring(xml)
            parts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            text = "\n".join(part for part in parts if part)
            if text.strip():
                return text
        except Exception:  # noqa: BLE001
            pass
    return data.decode("utf-8", errors="ignore")


def _journey(source: str, as_of: str | None = None) -> List[Dict[str, Any]]:
    from server.services import clock as clock_svc

    # Use prototype as-of date (not wall-clock calendar day) so Nov journeys don't show Oct.
    t0 = datetime.fromisoformat(clock_svc.stamp(as_of))
    stamps = [t0, t0, t0 + timedelta(seconds=1), t0 + timedelta(seconds=1), t0 + timedelta(seconds=2)]
    labels = [
        ("received", f"Received from {source}"),
        ("read", "Read document"),
        ("mapped", "Mapped"),
        ("validated", "Validated"),
        ("stored", "Stored"),
    ]
    return [
        {"key": k, "label": lab, "at": stamps[i].isoformat(timespec="seconds"), "source": source}
        for i, (k, lab) in enumerate(labels)
    ]


def _mappings_from_fixture(store: Store, fix: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "sourceSystem": m.get("source_system"),
            "sourceField": m.get("source_field"),
            "multiplierField": m["multiplier_field"],
            "value": m["value"],
            "status": m["status"],
            "confidence": m.get("confidence"),
        }
        for m in store.fixture_mappings(fix["id"])
    ]


def _apply_salary_revision(
    store: Store,
    emp: Dict[str, Any],
    extracted: Dict[str, Any],
    as_of: str,
    source: str,
    *,
    file_name: Optional[str] = None,
) -> None:
    """Keep the new base from a hike letter, record any bonus, and close the salary issue."""
    monthly = extracted.get("monthlyBase")
    if monthly is None and extracted.get("annualSalary"):
        monthly = float(extracted["annualSalary"]) / 12
    bonus = extracted.get("oneTimePaymentAmount")
    if monthly is None and not bonus:
        return
    if monthly is not None:
        monthly = float(monthly)
        store.update_employee_fields(
            emp["id"], base_salary=monthly, source=source, changed_this_cycle=1, edited_by_you=1
        )
        store.upsert_hr_employee(
            emp["id"],
            base_salary=monthly,
            updated_at=f"{as_of[:10]}T12:00:00",
            updated_by="HR tool",
        )
        store.log_change(
            emp["id"], "base_salary", emp["base_salary"], monthly, source=source, as_of=as_of
        )
    if bonus:
        bonus = float(bonus)
        existing = store.one_time_payments(emp["id"], as_of)
        already = any(
            abs(float(p.get("amount") or 0) - bonus) < 0.5
            and (p.get("type") == "Bonus" or "bonus" in (p.get("label") or "").lower())
            for p in existing
        )
        if not already:
            store.add_one_time_payment(
                emp["id"],
                type_="Bonus",
                label="Performance bonus",
                amount=bonus,
                recorded_on=as_of,
                source=source,
                document_name=file_name or "salary_revision.pdf",
            )
    base_lbl = rules_svc.fmt_money(emp["currency"], float(monthly if monthly is not None else emp["base_salary"]))
    bonus_lbl = rules_svc.fmt_money(emp["currency"], float(bonus)) if bonus else None
    if bonus_lbl:
        log = f"Salary revision letter attached; new base {base_lbl} and bonus {bonus_lbl}, {as_of}"
        matching = f"Salary revision letter, base {base_lbl} + bonus {bonus_lbl}"
        summary = f"{base_lbl} base + {bonus_lbl} bonus"
    else:
        log = f"Salary revision letter attached; new base {base_lbl} confirmed, {as_of}"
        matching = f"Salary revision letter, new base {base_lbl}"
        summary = f"New base {base_lbl}"
    from server.services.inputs import resolve_open_pay_confirmation

    resolve_open_pay_confirmation(
        store,
        {**emp, "base_salary": monthly if monthly is not None else emp["base_salary"]},
        as_of,
        resolution_log=log,
        matching_source=matching,
        change_summary=summary,
    )
    rules_svc.after_input_change(
        store, store.get_current_cycle(emp["customer_id"]), emp["id"], as_of=as_of, what="salary revision letter"
    )


def _salary_spike(emp: Dict[str, Any]) -> bool:
    """Base far above last cycle's pay — a bonus letter explains it as a one-off, not a new base."""
    sept = float(emp.get("september_pay") or 0)
    base = float(emp.get("base_salary") or 0)
    return sept > 0 and base > sept * 1.4


def _apply_bonus(
    store: Store,
    emp: Dict[str, Any],
    amount: float,
    as_of: str,
    source: str,
    *,
    file_name: Optional[str] = None,
) -> None:
    """Record a one-off bonus. A salary spike is split back to last cycle's base; everyone else keeps their base."""
    sept = float(emp.get("september_pay") or 0)
    spike = _salary_spike(emp)
    if spike:
        store.update_employee_fields(emp["id"], base_salary=sept, source=source, changed_this_cycle=1)
        store.upsert_hr_employee(
            emp["id"],
            base_salary=sept,
            updated_at=f"{as_of[:10]}T12:00:00",
            updated_by="HR tool",
        )
        store.log_change(emp["id"], "base_salary", emp["base_salary"], sept, source=source, as_of=as_of)
    existing = store.one_time_payments(emp["id"], as_of)
    already = any(
        abs(float(p.get("amount") or 0) - float(amount)) < 0.5
        and (p.get("type") == "Bonus" or "bonus" in (p.get("label") or "").lower())
        for p in existing
    )
    if not already:
        store.add_one_time_payment(
            emp["id"],
            type_="Bonus",
            label="Performance bonus",
            amount=amount,
            recorded_on=as_of,
            source=source,
            document_name=file_name or "bonus_letter.pdf",
        )
        store.update_employee_fields(emp["id"], edited_by_you=1, changed_this_cycle=1)
    if spike:
        cycle = store.get_current_cycle(emp["customer_id"])
        if cycle:
            for issue in store.list_issues(cycle["id"], status="open", as_of=as_of):
                if issue.get("employee_id") == emp["id"] and issue.get("kind") == "pay_confirmation":
                    store.resolve_issue(
                        issue["id"],
                        resolved_by="HR admin",
                        resolved_at=as_of,
                        resolution_log=(
                            f"Bonus letter attached; base {sept:g} + one-off {amount:g} by HR admin, {as_of}"
                        ),
                    )
                    line = store.current_review_line(cycle["id"], emp["id"])
                    if line:
                        amt = rules_svc.fmt_money(emp["currency"], amount)
                        base_lbl = rules_svc.fmt_money(emp["currency"], sept)
                        store.update_review_line(
                            line["id"],
                            matching_source=f"Bonus letter, one-off {amt}",
                            change_summary=f"{base_lbl} + {amt} bonus",
                        )
                    break
    elif not already and review_window_state(as_of) == "open":
        from server.services.review import ensure_edited_line

        ensure_edited_line(
            store,
            {**emp, "base_salary": emp.get("base_salary")},
            as_of=as_of,
            change_summary=f"Bonus {rules_svc.fmt_money(emp['currency'], amount)}",
            why_flagged="One-time payment – needs approval",
            matching_source=file_name or "Bonus letter",
        )
    rules_svc.after_input_change(
        store, store.get_current_cycle(emp["customer_id"]), emp["id"], as_of=as_of, what="bonus letter"
    )


def _apply_reimbursement(
    store: Store,
    emp: Dict[str, Any],
    amount: float,
    as_of: str,
    source: str,
    *,
    file_name: str = "travel_reimbursement_chloe.pdf",
) -> None:
    existing = store.one_time_payments(emp["id"], as_of)
    if not any("travel" in (p.get("label") or "").lower() or p.get("type") == "Reimbursement" for p in existing):
        store.add_one_time_payment(
            emp["id"],
            type_="Reimbursement",
            label="Client travel reimbursement",
            amount=amount,
            recorded_on=as_of,
            source=source,
            document_name=file_name or "travel_reimbursement_chloe.pdf",
        )
    rules_svc.after_input_change(
        store,
        store.get_current_cycle(emp["customer_id"]),
        emp["id"],
        as_of=as_of,
        what="travel reimbursement",
    )


def _apply_offer(store: Store, emp: Dict[str, Any], fix: Dict[str, Any], as_of: str, source: str) -> None:
    updates: Dict[str, Any] = {"source": source}
    if fix.get("monthly_base"):
        updates["base_salary"] = fix["monthly_base"]
        updates["september_pay"] = fix["monthly_base"]
    if fix.get("role"):
        updates["role"] = fix["role"]
    if fix.get("start_date"):
        updates["hire_date"] = fix["start_date"]
    store.update_employee_fields(emp["id"], **updates)
    mappings = store.fixture_mappings(fix["id"])
    missing = [m["multiplier_field"] for m in mappings if m["status"] == "missing"]
    # Keep any HR-owned extras already flagged (e.g. Manager)
    current = store.required_missing_fields(emp["id"])
    for f in missing:
        if f not in current:
            current.append(f)
    store.set_required_missing_fields(emp["id"], current)


def extract(
    store: Store,
    *,
    customer_id: str,
    as_of: str,
    file_name: Optional[str] = None,
    file_id: Optional[str] = None,
    access_token: Optional[str] = None,
    employee_id: Optional[str] = None,
    upload_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Download + extract + map. Never stores the access token. Falls back to known fixtures."""
    used_fallback = False
    note = None
    source = "Google Drive" if file_id else "Upload"
    filename = file_name or ""
    fixture_name = resolve_fixture_filename(filename)
    fix = store.get_fixture_by_filename(fixture_name) if fixture_name else None

    extracted: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    content = upload_bytes

    if file_id:
        try:
            content = llm_svc.download_drive_bytes(file_id, access_token or "")
        except PermissionError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as UI error / fallback
            error = str(exc)

    # Known fixtures keep their seed maps. Other demo letters (salary revision) are read from disk.
    if content is None and filename and not fix:
        demo_path = ROOT / "demo_documents" / Path(filename).name
        if demo_path.is_file():
            content = demo_path.read_bytes()

    # Prefer the file contents (upload or Drive). Fixture tables are only a fallback.
    if extracted is None and content:
        try:
            text = text_from_bytes(content, filename)
            parsed_first = parse_document_text(text) if text.strip() else {}
            # Hike letters must stay hike letters even when the model is on.
            if parsed_first.get("documentType") == "salary_revision":
                extracted = parsed_first
                used_fallback = True
                note = "Used rule-based extraction"
            elif text.strip() and llm_svc.llm_configured():
                try:
                    extracted = llm_svc.map_document(text)
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                    extracted = None
            if extracted is None:
                parsed = parse_document_text(text)
                if parsed.get("documentType") or parsed.get("annualSalary") or parsed.get(
                    "oneTimePaymentAmount"
                ):
                    extracted = parsed
                    used_fallback = True
                    note = "Used rule-based extraction"
        except Exception:  # noqa: BLE001
            extracted = None

    if extracted is None and DEMO_FALLBACK and fix:
        # Seed fixtures supply structured fields for known demo PDFs (presets only).
        used_fallback = True
        note = "Used rule-based extraction"
        otp_type = None
        if fix["doc_type"] == "bonus":
            otp_type = "Bonus"
        elif fix["doc_type"] == "reimbursement":
            otp_type = "Reimbursement"
        extracted = {
            "documentType": fix["doc_type"],
            "employeeName": fix["target_name"],
            "jobTitle": fix.get("role"),
            "startDate": fix.get("start_date"),
            "annualSalary": fix.get("annual_gross"),
            "currency": fix.get("currency"),
            "oneTimePaymentAmount": fix.get("bonus_amount"),
            "oneTimePaymentType": otp_type,
        }
    elif extracted is None and not fix:
        if error and "access" in error.lower():
            raise PermissionError("Couldn't open this file – check you have access")
        raise ValueError("This doesn't look like an offer, bonus or reimbursement letter")

    # Use fixture table mappings only when we did not already parse upload content
    use_fixture_maps = bool(fix) and not (content and extracted)
    if use_fixture_maps:
        mappings = _mappings_from_fixture(store, fix)
    else:
        mappings = llm_svc.extracted_to_mappings(extracted or {})
        # If parse worked but amount fields empty, fall back to fixture maps
        has_pay = any(
            m["multiplierField"]
            in ("Annual gross salary", "One-off bonus", "One-time payment", "Travel reimbursement")
            and m["status"] == "mapped"
            for m in mappings
        )
        if not has_pay and fix:
            mappings = _mappings_from_fixture(store, fix)
            use_fixture_maps = True

    if not any(
        m["multiplierField"]
        in ("Annual gross salary", "One-off bonus", "One-time payment", "Travel reimbursement")
        and m["status"] == "mapped"
        for m in mappings
    ) and fix is None:
        raise ValueError("Salary not found – please add it")

    steps = _journey(source, as_of)
    result = {
        "fileName": filename,
        "fileId": file_id,
        "docType": (fix or {}).get("doc_type") or (extracted or {}).get("documentType"),
        "usedFallback": used_fallback,
        "fallbackNote": note,
        "extracted": extracted,
        "mappings": mappings,
        "journeySteps": steps,
        "asOf": as_of,
    }

    if not employee_id:
        return result

    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")

    store.add_document(
        employee_id,
        file_name=filename or "document",
        source="Saved extraction" if used_fallback else source,
        as_of=as_of,
        file_id=file_id,
        doc_type=result["docType"],
        used_fallback=used_fallback,
        extracted=extracted,
        mappings=mappings,
    )
    store.add_journey_events(employee_id, steps)

    if (extracted or {}).get("documentType") == "salary_revision" or result["docType"] == "salary_revision":
        _apply_salary_revision(
            store, emp, extracted or {}, as_of, source, file_name=filename
        )
    elif fix and fix["doc_type"] in ("bonus", "reimbursement"):
        amount = float(fix.get("bonus_amount") or 0)
        if fix["doc_type"] == "reimbursement":
            _apply_reimbursement(store, emp, amount or 640, as_of, source, file_name=filename)
        else:
            _apply_bonus(store, emp, amount or 8000, as_of, source, file_name=filename)
    elif extracted and (extracted.get("oneTimePaymentAmount") or 0) and extracted.get("documentType") in (
        "bonus",
        "reimbursement",
    ):
        if extracted.get("documentType") == "reimbursement":
            _apply_reimbursement(
                store, emp, float(extracted["oneTimePaymentAmount"]), as_of, source, file_name=filename
            )
        else:
            _apply_bonus(
                store,
                emp,
                float(extracted["oneTimePaymentAmount"]),
                as_of,
                source,
                file_name=filename,
            )
    elif fix and fix["doc_type"] == "offer":
        _apply_offer(store, emp, fix, as_of, source)
    elif extracted and extracted.get("annualSalary"):
        monthly = float(extracted["annualSalary"]) / 12
        store.update_employee_fields(
            employee_id,
            base_salary=monthly,
            september_pay=monthly,
            source=source,
            role=extracted.get("jobTitle") or emp["role"],
        )

    return result
