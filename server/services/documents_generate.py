"""Generate sample payroll PDFs for the dynamic-inputs demo (reportlab or plain text fallback)."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional


def generate_sample_pdf(body: Dict[str, Any]) -> Dict[str, Any]:
    doc_type = (body.get("type") or body.get("docType") or "offer").lower()
    country = body.get("country") or "India"
    name = body.get("name") or "Sample Employee"
    amount = body.get("amount")
    start = body.get("startDate") or body.get("hireDate") or ""
    pay_month = body.get("payMonth") or ""
    omit: List[str] = list(body.get("omitFields") or [])
    role = body.get("role") or "Team Member"

    lines = [
        f"{doc_type.upper()} LETTER",
        f"Country: {country}",
        f"Employee: {name}",
        f"Role: {role}",
    ]
    if start:
        lines.append(f"Start date: {start}")
    if pay_month:
        lines.append(f"Pay month: {pay_month}")
    if amount is not None:
        lines.append(f"Amount: {amount}")
    if "PAN" not in omit and country == "India":
        lines.append("PAN: ABCDE1234F")
    if "Bank account" not in omit:
        lines.append("Bank account: 123456789012")
    if "IFSC" not in omit and country == "India":
        lines.append("IFSC: HDFC0000123")
    if "CPF" not in omit and country == "Brazil":
        lines.append("CPF: 123.456.789-09")
    if "Tax ID" not in omit and country == "Germany":
        lines.append("Tax ID: 12345678901")
    if "NI number" not in omit and country == "UK":
        lines.append("NI number: QQ123456C")
    if "Manager" not in omit:
        lines.append("Manager: Alex Manager")
    text = "\n".join(lines) + "\n"

    filename = f"{doc_type}_{name.lower().replace(' ', '_')}.pdf"
    pdf_bytes: Optional[bytes] = None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        y = 800
        for line in lines:
            c.drawString(72, y, line[:100])
            y -= 18
        c.save()
        pdf_bytes = buf.getvalue()
    except Exception:  # noqa: BLE001 — fallback without reportlab
        pdf_bytes = text.encode("utf-8")
        filename = filename.replace(".pdf", ".txt")

    import base64

    return {
        "fileName": filename,
        "contentType": "application/pdf" if filename.endswith(".pdf") else "text/plain",
        "base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "textPreview": text,
        "docType": doc_type,
    }
