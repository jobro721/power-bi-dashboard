#!/usr/bin/env python3
"""measures.py — Python twins of the 19 DAX measures in the Power BI model.

Every DAX measure in pbix/Model/tables/*.tmdl has a line-for-line Python
implementation here, so the numbers can be audited without Power BI
Desktop (which is Windows-only). DAX context rules are emulated for the
exact patterns the model uses:

  MAX(col)                      -> max over the rows matching the filter
  SUM(col)                      -> sum over the rows matching the filter
  CALCULATE(m, ALL(dim_period)) -> evaluate m with the period filter removed
  DIVIDE(a, b, BLANK())         -> a / b, or None when b == 0

Usage:
    python3 measures/measures.py            # run pinned-value verification
    python3 measures/measures.py show       # print the headline numbers

Verification compares against pinned_values.json (frozen 2026-09-11, from
federal-budget-data/data/budget.db, USAspending + Treasury + FRED, CC0).
Exit code 0 = all pinned values reproduced.
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
PINNED = HERE / "pinned_values.json"

F = lambda x: None if x == "" else float(x)


def load(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


class Model:
    """The 10 model tables as row lists (CSV headers == Power Query output)."""

    def __init__(self):
        self.obligation = load("agency_obligation_by_period.csv")
        self.agency_fy = load("agency_budgetary_resources.csv")
        self.gov = load("gov_budgetary_resources.csv")
        self.debt = load("debt_to_penny.csv")
        self.receipts = load("mts_receipts.csv")
        self.va_accounts = load("va_federal_accounts.csv")
        self.macro = load("macro_series.csv")
        self.active = load("fct_agency_active.csv")

    # ---------- fct_agency_obligations ----------

    def obligated_ytd(self, agency, fy, period):
        """MAX(oobligated) with agency + fy + period filters."""
        rows = [F(r["obligated"]) for r in self.obligation
                if r["code"] == agency and int(r["fiscal_year"]) == fy
                and int(r["period"]) == period]
        return max(rows) if rows else None

    def obligated_fye_last_actual(self, agency, fy):
        """CALCULATE([Obligated YTD], ALL(dim_period)) — period filter removed."""
        rows = [F(r["obligated"]) for r in self.obligation
                if r["code"] == agency and int(r["fiscal_year"]) == fy]
        return max(rows) if rows else None

    def period_delta(self, agency, fy, period):
        cur = self.obligated_ytd(agency, fy, period)
        prev = self.obligated_ytd(agency, fy, period - 1)
        return None if cur is None else cur - (prev or 0.0)

    # ---------- fct_agency_fy ----------

    def _fy_row(self, agency, fy):
        for r in self.agency_fy:
            if r["code"] == agency and int(r["fiscal_year"]) == fy:
                return r
        return None

    def budget_authority(self, agency, fy):
        r = self._fy_row(agency, fy)
        return F(r["agency_budgetary_resources"]) if r else None

    def obligated_fye(self, agency, fy):
        r = self._fy_row(agency, fy)
        return F(r["agency_total_obligated"]) if r else None

    def outlay_fye(self, agency, fy):
        r = self._fy_row(agency, fy)
        return F(r["agency_total_outlayed"]) if r else None

    def uob_fye(self, agency, fy):
        o, l = self.obligated_fye(agency, fy), self.outlay_fye(agency, fy)
        return None if o is None else o - l

    def pacing(self, agency, fy):
        """DIVIDE([Obligated FYE], [Budget Authority], BLANK())"""
        o, ba = self.obligated_fye(agency, fy), self.budget_authority(agency, fy)
        if o is None or not ba:
            return None
        return o / ba

    # ---------- fct_gov_resources ----------

    def gov_br_fy_estimate(self, fy, period):
        """'Gov Budgetary Resources (fy est.)' = MAX(total_budgetary_resources).
        NOT cumulative: each (fy, period) row is the *current full-year
        estimate*, which gets revised as the year progresses."""
        rows = [F(r["total_budgetary_resources"]) for r in self.gov
                if int(r["fiscal_year"]) == fy and int(r["fiscal_period"]) == period]
        return max(rows) if rows else None

    # ---------- fct_debt ----------

    def debt_latest(self):
        r = max(self.debt, key=lambda x: x["record_date"])
        return F(r["tot_pub_debt_out_amt"])

    def debt_public_latest(self):
        r = max(self.debt, key=lambda x: x["record_date"])
        return F(r["debt_held_public_amt"])

    # ---------- fct_receipts ----------

    def receipts_fytd(self, classification, date=None):
        rows = [r for r in self.receipts
                if r["classification_desc"] == classification
                and (date is None or r["record_date"] == date)]
        return max((F(r["fytd_amt"]) for r in rows), default=None)

    def receipts_current_month(self, classification, date=None):
        rows = [r for r in self.receipts
                if r["classification_desc"] == classification
                and (date is None or r["record_date"] == date)]
        return max((F(r["current_month_amt"]) for r in rows), default=None)

    # ---------- fct_va_accounts ----------

    def va_account_obligations(self, code=None):
        rows = [F(r["obligated_amount"]) for r in self.va_accounts
                if code is None or r["code"] == code]
        return sum(rows) if rows else None

    def va_account_uob(self, code=None):
        rows = [(F(r["obligated_amount"]) - F(r["gross_outlay_amount"]))
                for r in self.va_accounts if code is None or r["code"] == code]
        return sum(rows) if rows else None

    # ---------- fct_macro ----------

    def macro_latest(self, series):
        rows = [r for r in self.macro if r["series"] == series]
        r = max(rows, key=lambda x: x["date"])
        return F(r["value"])

    # ---------- fct_agency_active ----------

    def active_fy_outlays(self):
        return sum(F(r["outlay_amount"]) for r in self.active)

    def active_fy_obligations(self):
        return sum(F(r["obligated_amount"]) for r in self.active)

    def active_fy_budget_authority(self):
        return sum(F(r["budget_authority_amount"]) for r in self.active)


def verify(m):
    """Compare every pinned scenario against pinned_values.json."""
    pinned = json.loads(PINNED.read_text())
    fails = 0
    for name, want in pinned["values"].items():
        got = PINNED_CASES[name](m)
        ok = got is not None and abs(got - want) <= pinned["tolerance"]
        print(f"{'PASS' if ok else 'FAIL'}  {name:38s} "
              f"got={got:,.2f}  want={want:,.2f}" if got is not None
              else f"FAIL  {name:38s} got=None  want={want:,.2f}")
        fails += 0 if ok else 1
    print(f"\n{len(pinned['values']) - fails}/{len(pinned['values'])} pinned values reproduced")
    return fails


PINNED_CASES = {
    "VA FY26 P10 obligated YTD": lambda m: m.obligated_ytd("036", 2026, 10),
    "VA FY26 P2 obligated YTD": lambda m: m.obligated_ytd("036", 2026, 2),
    "VA FY26 P10 period delta": lambda m: m.period_delta("036", 2026, 10),
    "VA FY26 obligated FYE (last actual)": lambda m: m.obligated_fye_last_actual("036", 2026),
    "VA FY26 budget authority": lambda m: m.budget_authority("036", 2026),
    "VA FY26 obligated FYE": lambda m: m.obligated_fye("036", 2026),
    "VA FY26 outlay FYE": lambda m: m.outlay_fye("036", 2026),
    "VA FY26 UOB (FYE)": lambda m: m.uob_fye("036", 2026),
    "VA FY26 pacing %": lambda m: m.pacing("036", 2026),
    "Gov BR fy estimate FY23 P11": lambda m: m.gov_br_fy_estimate(2023, 11),
    "Total public debt (latest)": lambda m: m.debt_latest(),
    "Debt held by public (latest)": lambda m: m.debt_public_latest(),
    "Receipts Total FYTD (max in file)": lambda m: m.receipts_fytd("Total"),
    "VA 036-0102 account obligations": lambda m: m.va_account_obligations("036-0102"),
    "VA 036-0102 account UOB": lambda m: m.va_account_uob("036-0102"),
    "gs10 latest (2026-08-01)": lambda m: m.macro_latest("gs10"),
    "DFF latest (2026-09-09)": lambda m: m.macro_latest("dff"),
    "Active-FY outlays, 111 agencies": lambda m: m.active_fy_outlays(),
    "Active-FY obligations, 111 agencies": lambda m: m.active_fy_obligations(),
}


def show(m):
    print("Federal Budget, Hands-On — headline numbers (Python twins of the DAX measures)")
    print(f"  VA FY26 obligation curve: P2 {m.obligated_ytd('036', 2026, 2):,.0f} -> "
          f"P10 {m.obligated_ytd('036', 2026, 10):,.0f}")
    print(f"  VA FY26 BA {m.budget_authority('036', 2026):,.0f} | "
          f"pacing {m.pacing('036', 2026):.1%} | UOB {m.uob_fye('036', 2026):,.0f}")
    print(f"  Debt {m.debt_latest():,.0f} (public {m.debt_public_latest():,.0f})")
    print(f"  gs10 {m.macro_latest('gs10')} | dff {m.macro_latest('dff')}")
    print(f"  VA 036-0102 obligations {m.va_account_obligations('036-0102'):,.0f}")


if __name__ == "__main__":
    m = Model()
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show(m)
    else:
        sys.exit(1 if verify(m) else 0)
