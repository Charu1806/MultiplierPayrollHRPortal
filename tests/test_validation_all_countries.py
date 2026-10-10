"""Country validation findings — owners and formats from config."""

from server.services.findings import findings_for_new_hire, required_specs


def test_each_country_missing_fields_have_owners():
    for country in ("India", "UK", "Germany", "Brazil"):
        specs = required_specs(country)
        assert specs
        findings = findings_for_new_hire(
            country=country,
            manager=None,
            hire_date=None,
            salary=None,
            field_values={},
        )
        missing = [f for f in findings if f["rule"] == "required_missing"]
        assert missing
        for f in missing:
            assert f["owner"] in ("employee", "hr")
            assert f["field"]


def test_bad_pan_format_rejected():
    findings = findings_for_new_hire(
        country="India",
        manager="Ravi",
        hire_date="2026-10-01",
        salary=100000,
        field_values={"PAN": "BAD", "Bank account": "123456789012", "IFSC": "HDFC0000123"},
    )
    assert any(f["rule"] == "format_invalid" and f["field"] == "PAN" for f in findings)


def test_iban_and_sort_code_patterns():
    findings = findings_for_new_hire(
        country="UK",
        manager="Sam",
        hire_date="2026-10-01",
        salary=4000,
        field_values={"NI number": "QQ123456C", "Sort code": "12-34", "Bank account": "12345678"},
    )
    assert any(f["field"] == "Sort code" and f["rule"] == "format_invalid" for f in findings)

    ok = findings_for_new_hire(
        country="Germany",
        manager="Anna",
        hire_date="2026-10-01",
        salary=4200,
        field_values={
            "Tax ID": "12345678901",
            "IBAN": "DE89370400440532013000",
            "Tax class": "1",
        },
    )
    assert not any(f["rule"] == "format_invalid" for f in ok)
