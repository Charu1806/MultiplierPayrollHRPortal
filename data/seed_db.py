#!/usr/bin/env python3
"""
Seed the Payroll Clarity issue & cycle store from config/seed.json + config/cycle.json.

Creates 120 already-onboarded employees for Acme Tech (Workday), the October 2026
cycle, 3 open issues, document fixtures, reminders and the 6 review lines.

Usage:
  python3 data/seed_db.py
  python3 data/seed_db.py --db data/payroll_clarity.db --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / "schema.sql"
DEFAULT_DB = ROOT / "payroll_clarity.db"

sys.path.insert(0, str(ROOT))
from domain.config import cycle_config, seed_config  # noqa: E402

CYCLE_CFG = cycle_config()
SEED = seed_config()

CUSTOMER_ID = CYCLE_CFG["customer"]["id"]
OCT = CYCLE_CFG["cycles"]["october"]
CYCLE_ID = OCT["id"]
COUNTRY_TARGETS: dict[str, int] = CYCLE_CFG["countryTargets"]
CURRENCY: dict[str, str] = CYCLE_CFG["currencies"]

# Realistic monthly base bands (last approved September)
PAY_BANDS = {
    "India": (75000, 180000),
    "UK": (2800, 6500),
    "Germany": (3200, 6200),
    "Brazil": (9000, 22000),
}

ROLES = {
    "India": [
        "Software Engineer", "Senior Software Engineer", "Frontend Engineer", "Backend Engineer",
        "DevOps Engineer", "Product Designer", "Product Manager", "People Ops Specialist",
        "Finance Analyst", "Customer Success Manager", "QA Engineer", "Data Analyst",
        "Engineering Manager", "Recruiter", "Technical Writer",
    ],
    "UK": [
        "Software Engineer", "Senior Software Engineer", "Staff Engineer", "Product Manager",
        "Designer", "Account Executive", "Customer Success Manager", "Finance Business Partner",
        "People Partner", "Data Scientist", "SRE", "Marketing Manager", "Legal Counsel", "Ops Coordinator",
    ],
    "Germany": [
        "Software Engineer", "Backend Engineer", "Frontend Engineer", "Product Designer",
        "Engineering Manager", "Data Engineer", "Compliance Specialist", "HR Generalist",
        "Sales Engineer", "QA Engineer", "IT Administrator", "Office Manager",
    ],
    "Brazil": [
        "Software Engineer", "Solutions Architect", "Support Engineer", "Account Manager",
        "Product Analyst", "Designer", "People Ops", "Finance Associate", "Infrastructure Engineer",
        "QA Analyst", "Customer Success", "Recruiter",
    ],
}

FIRST = {
    "India": [
        "Aarav", "Vihaan", "Aditya", "Arjun", "Sai", "Krishna", "Ishaan", "Rohan",
        "Kavya", "Diya", "Isha", "Meera", "Sneha", "Pooja", "Neha", "Anika",
        "Kabir", "Dev", "Nikhil", "Varun", "Riya", "Tanvi", "Aisha", "Nisha",
        "Harsh", "Yash", "Kunal", "Amit", "Priya", "Shreya", "Deepa", "Sanjay",
        "Mohit", "Pankaj", "Suresh", "Lakshmi", "Sunita", "Ritu", "Gaurav", "Manish",
    ],
    "UK": [
        "Oliver", "Harry", "George", "Noah", "Jack", "Charlie", "Leo", "Arthur",
        "Amelia", "Olivia", "Isla", "Ava", "Mia", "Emily", "Sophia", "Grace",
        "James", "William", "Thomas", "Henry", "Alice", "Charlotte", "Ella", "Lucy",
        "Daniel", "Matthew", "Benjamin", "Samuel", "Hannah", "Jessica", "Sophie", "Chloe",
    ],
    "Germany": [
        "Lukas", "Leon", "Finn", "Paul", "Elias", "Noah", "Ben", "Jonas",
        "Emma", "Mia", "Hannah", "Emilia", "Lina", "Clara", "Sofia", "Anna",
        "Maximilian", "Felix", "Tim", "Jonas", "Laura", "Julia", "Marie", "Lea",
        "Tobias", "Niklas", "Jan", "Markus", "Sabine", "Petra", "Katharina", "Nina",
    ],
    "Brazil": [
        "Miguel", "Arthur", "Heitor", "Bernardo", "Davi", "Gabriel", "Pedro", "Lucas",
        "Alice", "Helena", "Laura", "Valentina", "Sophia", "Isabella", "Manuela", "Júlia",
        "Rafael", "Bruno", "Felipe", "Gustavo", "Camila", "Beatriz", "Larissa", "Fernanda",
        "Rodrigo", "André", "Marcos", "Carlos", "Juliana", "Patrícia", "Amanda", "Letícia",
    ],
}

LAST = {
    "India": [
        "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Nair", "Iyer",
        "Mehta", "Joshi", "Desai", "Chopra", "Banerjee", "Kapoor", "Malhotra", "Rao",
        "Verma", "Agarwal", "Pillai", "Menon", "Bhat", "Saxena", "Shah", "Kulkarni",
    ],
    "UK": [
        "Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies",
        "Patel", "Wright", "Evans", "Thomas", "Roberts", "Walker", "Robinson", "Thompson",
        "White", "Hughes", "Edwards", "Green", "Hall", "Clarke", "Harris", "Lewis",
    ],
    "Germany": [
        "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
        "Schulz", "Hoffmann", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder",
        "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger", "Hofmann", "Hartmann", "Lange",
    ],
    "Brazil": [
        "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira",
        "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes",
        "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento", "Moreira",
    ],
}

MANAGERS = {
    "India": ["Vikram Iyer", "Neha Kapoor", "Amit Desai"],
    "UK": ["Sarah Okonkwo", "James Wright", "Emily Clarke"],
    "Germany": ["Nora Weiss", "Markus Weber", "Julia Schneider"],
    "Brazil": ["Camila Rocha", "Rafael Costa", "Beatriz Lima"],
}


def reset_db(conn: sqlite3.Connection) -> None:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.executescript(SCHEMA.read_text())


def insert_customer_and_cycle(conn: sqlite3.Connection) -> None:
    cust = CYCLE_CFG["customer"]
    conn.execute(
        "INSERT INTO customers (id, name, hr_tool, employee_count) VALUES (?, ?, ?, ?)",
        (cust["id"], cust["name"], cust["hrTool"], cust["employeeCount"]),
    )
    conn.execute(
        """
        INSERT INTO payroll_cycles (
          id, customer_id, label, input_finalisation, approval_date,
          funding_due, submitted_date, pay_date, current_stage, approved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            CYCLE_ID, CUSTOMER_ID, OCT["label"], OCT["inputFinalisation"], OCT["approval"],
            OCT["fundingDue"], OCT["submitted"], OCT["payDate"], "Input finalisation",
        ),
    )


def slug_email(name: str, used: set[str]) -> str:
    base = (
        name.lower()
        .replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss")
        .replace("ú", "u").replace("í", "i").replace("á", "a").replace("é", "e").replace("ó", "o")
        .replace(" ", ".")
    )
    email = f"{base}@acmetech.example"
    n = 2
    while email in used:
        email = f"{base}{n}@acmetech.example"
        n += 1
    used.add(email)
    return email


def insert_employee(conn: sqlite3.Connection, emp: dict, used_emails: set[str]) -> None:
    email = emp.get("workEmail") or slug_email(emp["name"], used_emails)
    if emp.get("workEmail"):
        used_emails.add(email)
    conn.execute(
        """
        INSERT INTO employees (
          id, customer_id, name, role, country, currency, september_pay, base_salary,
          allowances, unpaid_leave_days, date_added, is_new, status, source, work_email,
          hire_date, manager_name, changed_this_cycle, matched_source, edited_by_you, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 'Active', 'Workday', ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            emp["id"], CUSTOMER_ID, emp["name"], emp["role"], emp["country"],
            CURRENCY[emp["country"]], emp["septemberPay"], emp.get("baseSalary", emp["septemberPay"]),
            emp.get("allowances", 0), emp.get("unpaidLeaveDays", 0),
            email, emp.get("hireDate", "2024-01-15"), emp.get("manager"),
            1 if emp.get("changedThisCycle") else 0, emp.get("matchedSource"), emp.get("notes"),
        ),
    )
    for field in emp.get("missing", []):
        conn.execute(
            "INSERT INTO employee_missing_fields (employee_id, field_name) VALUES (?, ?)",
            (emp["id"], field),
        )


def generate_fillers(rng: random.Random, named: list[dict]) -> list[dict]:
    """Generate remaining employees so country totals hit the config targets."""
    named_by_country = {c: 0 for c in COUNTRY_TARGETS}
    used_names = {e["name"] for e in named}
    for e in named:
        named_by_country[e["country"]] += 1

    fillers: list[dict] = []
    seq = 1
    for country, target in COUNTRY_TARGETS.items():
        need = target - named_by_country[country]
        lo, hi = PAY_BANDS[country]
        for _ in range(need):
            for _attempt in range(200):
                name = f"{rng.choice(FIRST[country])} {rng.choice(LAST[country])}"
                if name not in used_names:
                    break
            else:
                name = f"{rng.choice(FIRST[country])} {rng.choice(LAST[country])} {seq}"
            used_names.add(name)
            pay = rng.randint(lo, hi)
            if country == "India":
                pay = round(pay / 500) * 500
            elif country == "Brazil":
                pay = round(pay / 100) * 100
            else:
                pay = round(pay / 50) * 50
            fillers.append(
                {
                    "id": f"emp_gen_{seq:03d}",
                    "name": name,
                    "role": rng.choice(ROLES[country]),
                    "country": country,
                    "septemberPay": pay,
                    "baseSalary": pay,
                    "missing": [],
                    "notes": "Already onboarded · no changes this cycle",
                    "manager": rng.choice(MANAGERS[country]),
                    "hireDate": f"20{rng.randint(20, 25)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                }
            )
            seq += 1

    # 32 of the fillers changed this cycle and were auto-reconciled to a source
    recon = SEED["reconciledFillers"]
    picks = rng.sample(range(len(fillers)), recon["count"])
    for i in picks:
        fillers[i]["changedThisCycle"] = True
        fillers[i]["matchedSource"] = rng.choice(recon["sources"])
        fillers[i]["notes"] = "Changed this cycle · matched to a source automatically"
    return fillers


def insert_one_time_payments(conn: sqlite3.Connection) -> None:
    for p in SEED["oneTimePayments"]:
        conn.execute(
            """
            INSERT INTO one_time_payments (id, employee_id, type, label, amount, recorded_on, document_name, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (p["id"], p["employeeId"], p["type"], p["label"], p["amount"], p["recordedOn"], p.get("documentName"), p["source"]),
        )


def insert_issues(conn: sqlite3.Connection) -> None:
    for i in SEED["issues"]:
        conn.execute(
            """
            INSERT INTO issues (
              id, cycle_id, title, severity, employee_id, country, owner,
              deadline, source, impact, detail, ai_note, kind, created_on, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'open')
            """,
            (
                i["id"], CYCLE_ID, i["title"], i["severity"], i.get("employeeId"), i["country"], i["owner"],
                i["deadline"], i["source"], i["impact"], i.get("detail"), i.get("aiNote"), i.get("kind", "missing_fields"),
            ),
        )


def insert_reminders(conn: sqlite3.Connection) -> None:
    for order, r in enumerate(SEED["reminders"], start=1):
        conn.execute(
            "INSERT INTO cycle_reminders (id, cycle_id, title, deadline, owner, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
            (r["id"], CYCLE_ID, r["title"], r["deadline"], r["owner"], order),
        )


def insert_documents(conn: sqlite3.Connection) -> None:
    for d in SEED["documents"]:
        conn.execute(
            """
            INSERT INTO document_fixtures (
              id, filename, doc_type, target_name, country, role, start_date,
              annual_gross, currency, monthly_base, bonus_amount, all_fields_ok,
              resolves_issue_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                d["id"], d["filename"], d["docType"], d["targetName"], d.get("country"), d.get("role"),
                d.get("startDate"), d.get("annualGross"), d.get("currency"), d.get("monthlyBase"),
                d.get("bonusAmount"), 1 if d.get("allFieldsOk") else 0, d.get("resolvesIssueId"), d.get("notes"),
            ),
        )
        for order, (src, sf, mf, val, status, conf) in enumerate(d["mappings"], start=1):
            conn.execute(
                """
                INSERT INTO document_field_mappings (
                  document_id, source_system, source_field, multiplier_field, value, status, confidence, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (d["id"], src, sf, mf, val, status, conf, order),
            )


def insert_review_lines(conn: sqlite3.Connection, employees_by_id: dict[str, dict]) -> None:
    for order, line in enumerate(SEED["reviewLines"], start=1):
        emp = employees_by_id[line["employeeId"]]
        conn.execute(
            """
            INSERT INTO review_lines (
              id, cycle_id, employee_id, employee_name, country, change_summary, why_flagged,
              matching_source, matching_source_resolved, linked_issue_id, origin, created_on, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed', NULL, ?)
            """,
            (
                line["id"], CYCLE_ID, emp["id"], emp["name"], emp["country"], line["change"], line["why"],
                line["matchingSource"], line.get("matchingSourceResolved"), line.get("linkedIssueId"), order,
            ),
        )


def write_meta(conn: sqlite3.Connection, rng_seed: int) -> None:
    meta = {
        "dataset": "Payroll Clarity illustrative seed",
        "customer": CYCLE_CFG["customer"]["name"],
        "hr_tool": CYCLE_CFG["customer"]["hrTool"],
        "cycle": OCT["label"],
        "prototype_baseline_date": CYCLE_CFG["defaultPrototypeDate"],
        "prototype_date": CYCLE_CFG["defaultPrototypeDate"],
        "employee_total": str(CYCLE_CFG["customer"]["employeeCount"]),
        "countries": json.dumps(COUNTRY_TARGETS),
        "illustrative": "true",
        "rng_seed": str(rng_seed),
        "sources": "context.md, config/seed.json, config/cycle.json, config/rules.json",
    }
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", list(meta.items()))


def verify(conn: sqlite3.Connection, quiet: bool = False) -> None:
    total = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    by_country = dict(
        conn.execute("SELECT country, COUNT(*) FROM employees GROUP BY country ORDER BY country").fetchall()
    )
    issues = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'open'").fetchone()[0]
    named = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE id LIKE 'emp_%' AND id NOT LIKE 'emp_gen_%'"
    ).fetchone()[0]
    changed = conn.execute("SELECT COUNT(*) FROM employees WHERE changed_this_cycle = 1").fetchone()[0]
    matched = conn.execute("SELECT COUNT(*) FROM employees WHERE matched_source IS NOT NULL").fetchone()[0]
    lines = conn.execute("SELECT COUNT(*) FROM review_lines").fetchone()[0]
    expected_total = CYCLE_CFG["customer"]["employeeCount"]
    expected_named = len(SEED["employees"])
    expected_issues = len(SEED["issues"])
    if not quiet:
        print("── Verification ──")
        print(f"  Employees total: {total} (expected {expected_total})")
        print(f"  By country:      {by_country}")
        print(f"  Named seeds:     {named} (expected {expected_named})")
        print(f"  Open issues:     {issues} (expected {expected_issues})")
        print(f"  Changed / matched / need check: {changed} / {matched} / {lines} (expected 38 / 32 / 6)")
        print(f"  Documents:       {conn.execute('SELECT COUNT(*) FROM document_fixtures').fetchone()[0]}")
    assert total == expected_total, f"Expected {expected_total} employees, got {total}"
    assert by_country == COUNTRY_TARGETS, f"Country mismatch: {by_country}"
    assert issues == expected_issues
    assert named == expected_named
    assert changed == 38 and matched == 32 and lines == 6
    bad = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE date_added IS NOT NULL OR is_new != 0"
    ).fetchone()[0]
    assert bad == 0, "All seeded employees must be already onboarded (date_added NULL, is_new 0)"
    if not quiet:
        print("  OK — all checks passed")


def seed_database(db_path: Path, rng_seed: int = 42, quiet: bool = False) -> None:
    """Create (or recreate) the store at db_path from config. Used by the CLI and POST /api/demo/reset."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(rng_seed)
    conn = sqlite3.connect(str(db_path))
    try:
        reset_db(conn)
        insert_customer_and_cycle(conn)
        used_emails: set[str] = set()
        named = SEED["employees"]
        for emp in named:
            insert_employee(conn, emp, used_emails)
        for emp in generate_fillers(rng, named):
            insert_employee(conn, emp, used_emails)
        insert_one_time_payments(conn)
        insert_issues(conn)
        insert_reminders(conn)
        insert_documents(conn)
        insert_review_lines(conn, {e["id"]: e for e in named})
        write_meta(conn, rng_seed)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        verify(conn, quiet=quiet)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Payroll Clarity illustrative DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for fillers")
    args = parser.parse_args()
    seed_database(args.db, args.seed)
    print(f"\nDatabase written: {args.db}")


if __name__ == "__main__":
    main()
