# Source Data Profile

Stage 1 investigation results for the two provided BigQuery source
tables. All figures below are verified findings, not assumptions. Full
rationale and decisions based on these findings live in `DECISIONS.md`;
schema-level detail lives in `DATA_DICTIONARY.md`. This file is the
single-page factual summary of what was found.

---

## Citi Bike — `nyu-datasets.citibike.m_daily_trips`

| Fact | Value |
|---|---|
| Source table | `nyu-datasets.citibike.m_daily_trips` |
| Date range | 2013-06-01 through 2026-05-31 |
| Row count | 4,738 daily records |
| Grain | One row per calendar date (pre-aggregated daily table, not trip-level) |
| Missing calendar dates | 10 — see list below |
| Rider-type reconciliation | 251 days show anomalies, concentrated in 2016–2017; most differences appear small but some larger differences were also observed — full distribution not yet documented |
| Geography totals | Reconcile exactly |

**Missing calendar dates (10 total):**
2016-01-23, 2016-01-24, 2016-01-25, 2016-01-26, 2017-02-09, 2017-03-14,
2017-03-15, 2017-03-16, 2021-02-02, 2026-02-23.

No cause is speculated for either the missing dates or the rider-type
anomalies. Both are documented as known observations; see `DECISIONS.md`
D-011, D-012, and D-013 for how they are handled.

---

## Weather — `nyu-datasets.weather.m_weather_daily_nyc`

| Fact | Value |
|---|---|
| Source table | `nyu-datasets.weather.m_weather_daily_nyc` |
| Date range | 1876-01-01 through 2026-05-29 |
| Row count | 54,912 daily records |
| Grain | One record per date |
| Duplicate dates | None found |
| Missing calendar dates | 24 (confirmed by count: 54,936 calendar days in range vs. 54,912 unique dates) — specific dates and cause unresolved |

See `DECISIONS.md` D-016 for detail. The count of 24 missing dates is a
verified fact, not a guess; the specific missing dates themselves have
not yet been enumerated.

---

## Join Validation

| Fact | Value |
|---|---|
| Join key | `date` |
| Citi Bike days | 4,738 |
| Successful weather matches | 4,736 |
| Unmatched dates | 2026-05-30, 2026-05-31 |

These 2 dates are unmatched because the weather table's data currently
ends 2026-05-29 — two days before the Citi Bike table's most recent date
(2026-05-31). This is fully explained by the two tables' differing as-of
dates. See `DECISIONS.md` D-014 and D-015.

---

## Cross-references

- `DATA_DICTIONARY.md` Sections 1a, 4, 5, 6 — full schema-level detail and
  data-quality check mapping.
- `DECISIONS.md` D-004, D-005, D-009 through D-016 — decisions and
  rationale based on these findings.
