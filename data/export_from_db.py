#!/usr/bin/env python3
"""export_from_db.py — build the Power BI source CSVs from the budget.db spine.

Reads  ../federal-budget-data/data/budget.db  (sibling repo)
Writes the 10 CSVs in data/ that the PBIT's Power Query layer loads.

Re-runnable; output is deterministic (same DB -> same bytes).
The FRED series tables (date/value) are merged into one long
macro_series.csv with a `series` column so the model needs one table.
"""
import csv
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE.parent.parent / "federal-budget-data" / "data" / "budget.db"

# csv name -> sql (ORDER BY keeps output deterministic)
EXPORTS = {
    "toptier_agencies.csv":
        "SELECT code, name, abbreviation FROM toptier_agencies ORDER BY code",
    "fct_agency_active.csv":
        "SELECT code, active_fy, outlay_amount, obligated_amount, "
        "budget_authority_amount FROM toptier_agencies ORDER BY code",
    "agency_obligation_by_period.csv":
        "SELECT code, fiscal_year, period, obligated "
        "FROM agency_obligation_by_period ORDER BY code, fiscal_year, period",
    "agency_budgetary_resources.csv":
        "SELECT code, fiscal_year, agency_budgetary_resources, "
        "agency_total_obligated, agency_total_outlayed "
        "FROM agency_budgetary_resources ORDER BY code, fiscal_year",
    "gov_budgetary_resources.csv":
        "SELECT fiscal_year, fiscal_period, total_budgetary_resources "
        "FROM gov_budgetary_resources ORDER BY fiscal_year, fiscal_period",
    "debt_to_penny.csv":
        "SELECT record_date, tot_pub_debt_out_amt, debt_held_public_amt, "
        "intragov_hold_amt FROM debt_to_penny ORDER BY record_date",
    "mts_receipts.csv":
        "SELECT record_date, classification_desc, line_code_nbr, "
        "current_month_amt, fytd_amt, prior_fytd_amt "
        "FROM mts_receipts ORDER BY record_date, classification_id",
    "va_federal_accounts.csv":
        "SELECT code, name, obligated_amount, gross_outlay_amount "
        "FROM va_federal_accounts ORDER BY code",
}

MACRO_SERIES = ["gs10", "dff", "fgexpnd", "m2sl", "t10y3m", "unrate", "cpiaucsl"]


def main():
    if not DB.exists():
        sys.exit(f"missing {DB} — keep federal-budget-data as a sibling")
    con = sqlite3.connect(DB)
    for name, sql in EXPORTS.items():
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        with open(HERE / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")
    # merged macro long table (7 FRED series -> 3-column file)
    rows = []
    for s in MACRO_SERIES:
        rows += [(s, d, v) for d, v in
                 con.execute(f"SELECT date, value FROM {s} ORDER BY date")]
    with open(HERE / "macro_series.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["series", "date", "value"])
        w.writerows(rows)
    print(f"macro_series.csv: {len(rows)} rows ({len(MACRO_SERIES)} series)")


if __name__ == "__main__":
    main()
