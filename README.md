# Power BI Dashboard — The Federal Budget, Hands-On

A production-style Power BI semantic model for US federal budget data: **star schema,
19 DAX measures, a Modern-Ledger theme, and a parameterized data folder** — packaged as
both diffable source (`.pbixproj` + TMDL) and a compiled `.pbit` you can open in
Power BI Desktop.

This is the Power BI leg of the [jo_projects](../) federal-budget portfolio. The data
spine lives in the sibling repo [`federal-budget-data`](../federal-budget-data)
(USAspending API v2 + Treasury fiscaldata + FRED — all public domain, pulled and
frozen 2026-09-11).

## Why this shape

- **`.pbit` = a zip of plain text.** The model is TMDL (Textual Metadata Definition
  Language) — every table, column, measure, and relationship is a line you can read,
  review, and diff. That is the modern way to keep Power BI models under version
  control (pbi-tools, not binary `.pbix` blobs).
- **Star schema, not flat tables.** Two dimensions (`dim_agency`, `dim_period`) drive
  nine fact tables. Filters flow from dimensions to facts, which is what makes
  slicers and drillthroughs work.
- **`MAX`, not `SUM`, for cumulative values.** The obligation series from USAspending
  is already cumulative within each fiscal year; summing it would double-count.
- **Parameterized data folder.** `DataFolder` is a Power Query text parameter. Open
  the `.pbit`, pick the `data/` folder, refresh — no connection strings baked in.

## Quickstart

```
1. Install Power BI Desktop (free).
2. File > Open > select federal-budget.pbit.
3. When prompted for the DataFolder parameter, browse to this repo's data/ folder.
4. Refresh (Transform Data > Refresh). ~10s for 46K rows.
5. Build: drag dim_period[month] x Obligated YTD into a line chart;
   dim_agency[abbreviation] x Pacing % into a bar chart. The Welcome page
   lists the first four visuals.
```

No Power BI account or service needed — everything runs locally.

## The model

```
                    dim_agency (111)
                    |  |  |
        code        |  |  | code (1:1)
   +----------------+  |  +-----------------------+
   |                  |  |                         |
fct_agency_      fct_agency_fy             fct_agency_active
obligations       (30: BA/obligated/         (111: current-FY
(216: cumulative    outlay by FY)             outlays/oblig/BA)
 P1..P12 by FY)
   |
dim_period (12)  |
   |             +------------------------> fct_gov_resources (33)
   |
   +--> fct_debt (2,935 daily)   fct_receipts (1,221)
                            fct_va_accounts (44 TAS)
                            fct_macro (41,452: 7 FRED series)
```

| Table | Grain | Source CSV |
|---|---|---|
| `dim_agency` | top-tier agency (111) | `toptier_agencies.csv` |
| `dim_period` | fiscal month P1–P12 (static) | — (inline `#table`) |
| `fct_agency_obligations` | agency × FY × period, cumulative | `agency_obligation_by_period.csv` |
| `fct_agency_fy` | agency × FY totals (VA, DoD, DHS) | `agency_budgetary_resources.csv` |
| `fct_gov_resources` | government × FY × period | `gov_budgetary_resources.csv` |
| `fct_debt` | daily debt-to-the-penny | `debt_to_penny.csv` |
| `fct_receipts` | MTS Table 9, monthly | `mts_receipts.csv` |
| `fct_va_accounts` | VA federal accounts (TAS) | `va_federal_accounts.csv` |
| `fct_macro` | FRED series long form | `macro_series.csv` |
| `fct_agency_active` | 111 agencies, active-FY amounts | `fct_agency_active.csv` |

## The 19 DAX measures (each has a Python twin)

| Measure | DAX (abridged) | Twin |
|---|---|---|
| Obligated YTD | `MAX(fct_agency_obligations[obligated])` | `m.obligated_ytd(…)` |
| Obligated FYE (last actual) | `CALCULATE([Obligated YTD], ALL(dim_period))` | `m.obligated_fye_last_actual(…)` |
| Period Delta | `VAR cur = MAX(period) RETURN [Obligated YTD] − CALCULATE(…, dim_period[period] = cur−1)` | `m.period_delta(…)` |
| Budget Authority | `MAX(fct_agency_fy[budget_authority])` | `m.budget_authority(…)` |
| Obligated FYE / Outlay FYE | `MAX(…)` | `m.obligated_fye(…)` / `m.outlay_fye(…)` |
| UOB (FYE) | `[Obligated FYE] − [Outlay FYE]` | `m.uob_fye(…)` |
| Pacing % | `DIVIDE([Obligated FYE], [Budget Authority], BLANK())` | `m.pacing(…)` |
| Gov Budgetary Resources (cum.) | `MAX(…)` | `m.gov_br_cumulative(…)` |
| Total Public Debt / Debt Held by the Public | `MAX(…)` | `m.debt_latest(…)` / `m.debt_public_latest(…)` |
| Receipts (FYTD) / (Current Month) | `MAX(…)` | `m.receipts_fytd(…)` / `m.receipts_current_month(…)` |
| VA Account Obligations / UOB | `SUM(…)` | `m.va_account_obligations(…)` / `m.va_account_uob(…)` |
| Macro Value (latest) | `MAX(fct_macro[value])` | `m.macro_latest(…)` |
| Active-FY Outlays / Obligations / Budget Authority (111 agencies) | `SUM(…)` | `m.active_fy_…(…)` |

### Verifying the numbers without Power BI

```
python3 measures/measures.py        # 19/19 pinned values reproduced
python3 measures/measures.py show   # headline numbers
```

`measures/pinned_values.json` freezes the 2026-09-11 values (tolerance $0.01), e.g.
VA FY26: BA $525.64bn, obligated FYE $371.05bn, outlay FYE $382.39bn,
UOB −$11.34bn, pacing 70.6%; debt $40.07T; gs10 4.68; dff 3.63. If the CSVs are
regenerated from a fresh DB pull, the twins re-verify against these anchors.

## Rebuilding the CSVs

```
python3 data/export_from_db.py     # needs ../federal-budget-data/data/budget.db
```

## Recompiling the `.pbit`

The source of truth is `pbix/` (`.pbixproj.json` + TMDL). The compiled artifact is
`federal-budget.pbit`. Recompile with the official pbi-tools container (no Power BI
license needed to compile):

```
docker run --rm -v $PWD:/work -w /work ghcr.io/pbi-tools/pbi-tools-core \
  /app/pbi-tools/pbi-tools.core compile -folder ./pbix -format PBIT \
  -outPath ./federal-budget.pbit -overwrite
```

**Status:** compiled clean with pbi-tools.core 1.2.0 (`.NET 8`); the package contains
`/DataModelSchema` (10 tables, 19 measures, 5 relationships), the report layout, and
the ModernLedger theme. Opening the `.pbit` in Power BI Desktop (Windows) is the
final human-in-the-loop step — the model uses only standard import-mode queries.

## Repo layout

```
pbix/                       # source of truth: .pbixproj.json + TMDL + report + theme
  Model/
    database.tmdl           # compatibilityLevel 1550
    model.tmdl              # query order + ref table list
    expressions.tmdl        # DataFolder parameter (IsParameterQuery)
    relationships.tmdl      # 5 relationships
    tables/*.tmdl           # 10 tables; columns, partitions (Power Query M), measures
  Report/                   # one Welcome page (textbox) — the visual starting point
  StaticResources/…/BaseThemes/ModernLedger.json
data/                       # 10 source CSVs (frozen 2026-09-11) + export_from_db.py
measures/                   # Python twins + pinned values
federal-budget.pbit         # compiled artifact
```

## Data & license

All inputs are public domain / CC0 (US government data via USAspending,
fiscaldata.treasury.gov, and FRED). Frozen snapshot 2026-09-11. No PII, no CUI.
