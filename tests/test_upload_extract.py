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
