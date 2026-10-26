# Dashboard Year Selection Feature

## Overview

The UC44 dashboard now supports selecting the year (reporting period) for which emission factors are used in the KPI calculations. This allows users to:
- Compare emissions across different years by swapping emission factors
- Verify calculations against historical data
- Support multi-year reporting workflows

All KPIs, charts, and the detail table recalculate immediately when the year is changed.

## Architecture

### Backend Changes

#### 1. **Service Layer** (`app/backend/app/services/`)

- **`warengruppen.py`**
  - New function: `available_years()` → returns sorted list of years for which emission factors exist in the DB (or Excel fallback)
  - Updated: `ef_lookup(jahr: Optional[int] = None)` now accepts a year parameter; defaults to the most recent if `None`

- **`dashboard.py`**
  - Updated: `build(state, jahr=None)` signature now accepts an optional year parameter
  - Pass the year to both `_ef_lookup(jahr)` and `_ka_ef_lookup(jahr)` for Warengruppen and cost-category (Kostenart) lookups
  - Returns available years + selected year in the `DashboardResponse`

#### 2. **API Layer** (`app/backend/app/api/`)

- **`dashboard.py`**
  - Updated endpoint: `GET /api/dashboard` now accepts an optional query parameter `jahr` (integer)
  - Passes the year to the service layer: `svc.build(get_state(), jahr=jahr)`

#### 3. **Schema** (`app/backend/app/schemas/models.py`)

- **`DashboardResponse`** model enhanced with two new fields:
  - `available_years: list[int] = []` – emission-factor years available in the catalog
  - `selected_year: Optional[int] = None` – the year the user (or API caller) selected for this request

### Frontend Changes

#### 1. **API Models** (`app/frontend/src/api/`)

- **`dashboard-response.ts`** – updated interface to reflect the new response fields

#### 2. **Dashboard Component** (`app/frontend/src/app/views/dashboard/`)

- **`dashboard.ts` (component logic)**
  - New signal: `selectedYear = signal<number | null>(null)` tracks the user's choice
  - Updated: `refresh(year?: number | null)` now accepts an optional year and passes it as a query parameter
  - New computed: `yearOptions()` builds a dropdown menu: `[{ value: null, label: 'Aktuell (neueste EF)' }, ...years]`
  - New method: `onYearChange(year)` handles year selection and triggers a dashboard refresh
  - Uses `HttpClient` directly instead of the generated service to reliably pass query parameters

- **`dashboard.html` (template)**
  - New year selector dropdown in the toolbar (positioned before the refresh button)
  - Linked to `yearOptions()` and `selectedYear()` via the generic `app-select` component

## Usage Flow

1. **User visits Dashboard**
   - Dashboard loads with the default year (most recent emission factors)
   - Year selector is populated with available years from the database

2. **User selects a different year**
   - Dropdown triggers `onYearChange()`
   - Component calls `refresh(selectedYear)` with the new year
   - Frontend sends `GET /api/dashboard?jahr=2023` (for example)

3. **Backend processes the request**
   - `dashboard.build(state, jahr=2023)` runs
   - Both WG and cost-category emission factors are looked up for year 2023
   - KPIs, charts, and detail tables recalculate using the 2023 factors
   - Response includes `selected_year: 2023` + `available_years: [2023, 2024, 2025, ...]`

4. **Frontend updates display**
   - All KPIs, bar chart, histogram, and detail table refresh immediately
   - Year selector reflects the new selection
   - Change log and Sankey diagram remain unchanged (they are flow/audit data, not affected by year)

## Implementation Details

### Emission Factor Lookup Order

**`ef_lookup(jahr=None)`:**
- If `jahr` is provided and exists in the database for the Warengruppe, use it
- Otherwise, use the most recent year available for that Warengruppe

### Available Years Discovery

**`available_years()`:**
- Queries the `Emissionsfaktor` table to find all unique `jahr` values
- Falls back to scanning the Excel file if the table is unseeded
- Returns a sorted list `[2020, 2021, ..., 2024]`

### Query Parameter Passing

The frontend uses `HttpClient` + `HttpParams` directly (instead of the generated service) to ensure query parameters are reliably encoded:

```typescript
const params = new HttpParams({
  fromObject: effectiveYear != null ? { jahr: String(effectiveYear) } : {},
});
this.http.get<DashboardResponse>('/api/dashboard', { params }).subscribe({...});
```

## Testing

A regression test (`tests/test_dashboard_year_selection.py`) verifies:
- The `build()` function correctly forwards the `jahr` parameter to `ef_lookup()`
- The service is called with the selected year when provided

**Run the test:**
```bash
.venv/Scripts/python.exe -m unittest tests.test_dashboard_year_selection -v
```

## Notes

- **No changes to the Excel export** – the export includes the selected year in the filename or metadata if desired (future enhancement)
- **Sankey diagram is year-agnostic** – it shows *flows* (user decisions), not values, so year selection doesn't affect it
- **Review stage is unaffected** – year selection only applies to the dashboard; the KI-Prüfung (plausibility/prediction) uses the latest factors
- **Fallback behavior** – if no year is selected (`jahr=null`), the most recent year is used automatically

## Agreed Scope

Per the stakeholder agreement (2026-06-05+), year selection was integrated into the final Dashboard as a single, optional selector. This allows multi-year reporting and analysis without requiring separate re-runs of the models.
