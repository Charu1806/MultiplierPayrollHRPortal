"""Upload-from-computer extract path (demo_documents PDFs)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"
DEMO = ROOT / "demo_documents"


@pytest.fixture()
def client(tmp_path):
    db = tmp_path / "upload.db"
    subprocess.check_call(
        [sys.executable, str(SEED), "--db", str(db), "--seed", "42"],
        cwd=str(ROOT),
    )
    from server.app import create_app
    from server.db.connection import set_db_path

    set_db_path(db)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_bonus_letter_on_any_employee_keeps_base(client):
    """A bonus letter adds a one-off. It only rewrites base when pay is a spike."""
    before = client.get(
        "/api/employees/emp_chloe?asOf=2026-10-13",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()
    base_before = before["salary"]["base"]
    path = DEMO / "bonus_letter_james_patel_oct.pdf"
    with path.open("rb") as fh:
        res = client.post(
            "/api/documents/extract",
            data={
                "asOf": "2026-10-13",
                "employeeId": "emp_chloe",
                "file": (fh, path.name),
            },
            content_type="multipart/form-data",
            headers={"X-Customer-Id": "cust_acme"},
        )
    assert res.status_code == 200, res.get_json()
    after = client.get(
        "/api/employees/emp_chloe?asOf=2026-10-13",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()
    assert after["salary"]["base"] == base_before
    assert any(o["amount"] == 8000 and "bonus" in o["label"].lower() for o in after["oneOffs"])
    assert after["letters"]["bonus"]["fileName"]
    assert after["letters"]["offer"] is None
    assert after["letters"]["hike"] is None
    pdf = client.get(
        f"/api/documents/{after['letters']['bonus']['id']}/file",
        headers={"X-Customer-Id": "cust_acme"},
    )
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"


def test_bonus_letter_splits_a_salary_spike(client):
    path = DEMO / "bonus_letter_james_patel_oct.pdf"
    with path.open("rb") as fh:
        res = client.post(
            "/api/documents/extract",
            data={
                "asOf": "2026-10-13",
                "employeeId": "emp_james",
                "file": (fh, path.name),
            },
            content_type="multipart/form-data",
            headers={"X-Customer-Id": "cust_acme"},
        )
    assert res.status_code == 200, res.get_json()
    emp = client.get(
        "/api/employees/emp_james?asOf=2026-10-13",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()
    assert emp["salary"]["base"] == 4000
    assert any(o["amount"] == 8000 for o in emp["oneOffs"])


def test_upload_bonus_pdf_from_demo_documents(client):
    path = DEMO / "bonus_letter_james_patel_oct.pdf"
    assert path.exists()
    with path.open("rb") as fh:
        res = client.post(
            "/api/documents/extract",
            data={"asOf": "2026-10-13", "file": (fh, path.name)},
            content_type="multipart/form-data",
            headers={"X-Customer-Id": "cust_acme"},
        )
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["fileName"] == path.name
    fields = {m["multiplierField"]: m for m in body["mappings"]}
    assert fields["Employee name"]["value"] == "James Patel"
    assert fields["One-off bonus"]["status"] == "mapped"


def test_drive_pick_downloads_with_token_and_reads_pdf(client, monkeypatch):
    path = DEMO / "offer_letter_aisha_khan_oct.pdf"
    pdf = path.read_bytes()
    seen = {}

    def fake_download(file_id, access_token):
        seen["file_id"] = file_id
        seen["access_token"] = access_token
        return pdf

    monkeypatch.setattr("server.services.llm.download_drive_bytes", fake_download)
    monkeypatch.setattr("server.services.llm.llm_configured", lambda: False)
    res = client.post(
        "/api/drive/extract",
        json={
            "asOf": "2026-10-13",
            "fileName": "Aisha offer.pdf",
            "fileId": "drive-file-1",
            "accessToken": "ya29.test-token",
        },
        headers={"X-Customer-Id": "cust_acme"},
    )
    assert res.status_code == 200, res.get_json()
    assert seen == {"file_id": "drive-file-1", "access_token": "ya29.test-token"}
    fields = {m["multiplierField"]: m for m in res.get_json()["mappings"]}
    assert fields["Employee name"]["value"] == "Aisha Khan"
    assert fields["Annual gross salary"]["status"] == "mapped"


def test_upload_offer_pdf_from_demo_documents(client):
    path = DEMO / "offer_letter_aisha_khan_oct.pdf"
    with path.open("rb") as fh:
        res = client.post(
            "/api/documents/extract",
            data={"asOf": "2026-10-13", "file": (fh, path.name)},
            content_type="multipart/form-data",
            headers={"X-Customer-Id": "cust_acme"},
        )
    assert res.status_code == 200, res.get_json()
    fields = {m["multiplierField"]: m for m in res.get_json()["mappings"]}
    assert fields["Employee name"]["value"] == "Aisha Khan"
    assert fields["Annual gross salary"]["status"] == "mapped"


def test_salary_revision_letter_sets_hike_and_bonus_and_resolves(client):
    path = DEMO / "salary_revision_james_patel.pdf"
    assert path.exists()
    with path.open("rb") as fh:
        res = client.post(
            "/api/documents/extract",
            data={
                "asOf": "2026-10-13",
                "employeeId": "emp_james",
                "file": (fh, path.name),
            },
            content_type="multipart/form-data",
            headers={"X-Customer-Id": "cust_acme"},
        )
    assert res.status_code == 200, res.get_json()
    emp = client.get(
        "/api/employees/emp_james?asOf=2026-10-13",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()
    assert emp["salary"]["base"] == 8000
    assert any(o["amount"] == 4000 for o in emp["oneOffs"])
    assert emp["letters"]["hike"]["fileName"]
    issues = client.get(
        "/api/issues?asOf=2026-10-13&status=open",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()["issues"]
    assert all(i["id"] != "issue_002" for i in issues)


def test_confirming_spiked_salary_resolves_issue(client):
    res = client.patch(
        "/api/employees/emp_james",
        json={"asOf": "2026-10-13", "baseSalary": 12000, "confirmAiCheck": True},
        headers={"X-Customer-Id": "cust_acme"},
    )
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["salary"]["base"] == 12000
    issues = client.get(
        "/api/issues?asOf=2026-10-13&status=open",
        headers={"X-Customer-Id": "cust_acme"},
    ).get_json()["issues"]
    assert all(i["id"] != "issue_002" for i in issues)
