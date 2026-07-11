# Engineering Journal

This is a personal, running journal of the investigation process —
what I looked into, what I found, what's still unresolved, and what I
want to remember to include in the final report. It is deliberately
informal and narrative.

This is **not** a duplicate of:
- `README.md` — the project's polished, public-facing overview (business
  question, goal, metrics, repo structure).
- `DECISIONS.md` — the formal, structured decision log (ADR-style: status,
  context, decision, alternatives). Every material decision still gets
  logged there; this journal is where I think out loud on the way to a
  decision, or just note something worth remembering.

When in doubt about exact figures, this file points to
`DATA_DICTIONARY.md` and `DECISIONS.md` rather than restating them.

---

## Stage 1 — Source Data Investigation

### Objective

Investigate and validate the provided Citi Bike and weather datasets
before designing or implementing the ETL pipeline. Establish verified
facts about the source data, identify data-quality issues, validate the
join strategy, and document all findings so later implementation is
based on evidence rather than assumptions.

### What I investigated

Instead of extracting public Citi Bike trip files, we confirmed the
project uses two provided BigQuery tables directly:
`nyu-datasets.citibike.m_daily_trips` and
`nyu-datasets.weather.m_weather_daily_nyc`. I checked each table's row
count, date range, grain, and duplicate-date status, tested whether known
totals (geography, rider-type) reconcile internally, and validated a
`date`-based join between the two tables.

### Verified Findings

- The Citi Bike table is a genuine surprise: it's **already
  pre-aggregated at daily grain**, not trip-level rows. That changes the
  shape of the whole pipeline — there may be much less "standardize a
  changing trip-level schema" work than the original plan assumed.
- It covers 2013-06-01 through 2026-05-31 (4,738 days), with 10 specific
  calendar dates missing. Geography totals reconcile exactly. Rider-type
  totals don't reconcile on 251 days concentrated in 2016–2017 — mostly
  small differences, but not uniformly, and I haven't characterized the
  full distribution yet.
- The weather table's history goes back to 1876 (!) — far longer than
  anything Citi Bike needs — with 54,912 records, one per date, no
  duplicates. Simple arithmetic on the confirmed range/count implies 24
  missing dates, but unlike the Citi Bike gap, I haven't pinned down which
  24 yet.
- Joining the two tables on `date` gives 4,736 matches out of 4,738 Citi
  Bike days (99.96%). The 2 misses are just the weather table not having
  caught up to the last 2 Citi Bike days yet — not a real defect.

Full verified figures: `DATA_DICTIONARY.md` Sections 1a, 4, 5. Full
decision log: `DECISIONS.md` D-004, D-005, D-009 through D-016. One-page
summary: `docs/source_data_profile.md`.

### Engineering Reflections

One of the biggest lessons from Stage 1 was that the Citi Bike dataset is
already aggregated to the daily level. Initially I assumed the project
would involve ingesting raw trip-level files and harmonizing schemas
across years. The investigation showed that the provided teaching dataset
has already performed much of that work.

This discovery changes the design of the ETL pipeline and reinforces an
important engineering lesson:

Never design a pipeline before understanding the source data.

### Lessons Learned

Stage 1 reinforced several important data engineering principles:
- Never assume the structure of a dataset based on its public source or documentation.
- Always profile data before designing an ETL pipeline.
- Validate record counts, date coverage, and reconciliation rules before writing transformations.
- Treat unexpected findings as evidence to investigate, not errors to immediately correct.
- Document assumptions separately from verified facts so future decisions remain traceable.

The investigation phase changed the direction of the project. Instead of
building an ETL pipeline around raw trip-level Citi Bike data, the design
will be based on validated daily summary tables already available in
BigQuery. This simplified the architecture while increasing confidence in
the correctness of later stages.

### Open questions

- What actually happened on the 10 missing Citi Bike dates, and the 24
  (not yet identified) missing weather dates? Real source-side gaps, or
  an artifact of how these tables were built? No cause assumed yet either
  way.
- Why don't rider-type totals reconcile on those 251 specific days, and
  why are some differences bigger than others? Is there a pattern (e.g.,
  tied to a schema or operational change around 2016–2017), or is it
  noise? Worth a closer look before writing this off.
- I still don't have column-level schema (names, types, PK candidates)
  for either table — need BigQuery schema access to move forward on
  Stage 3 planning.
- Given the Citi Bike table is already daily-grain, do I even need a
  "trip-level canonical schema" step, or does that collapse into
  something much simpler? Not resolved — flagged in
  `DATA_DICTIONARY.md` Section 2, but not decided.

### Next Stage

Stage 2 will focus on building the first version of the ETL pipeline.

Objectives:
- Connect to the provided BigQuery datasets.
- Read the Citi Bike and weather tables using configurable settings.
- Implement extraction logging and validation.
- Preserve the validated assumptions established during Stage 1.

### For the final report

- The "source data turned out to already be aggregated" finding is worth
  its own short section — it's a genuine, honest twist in the project's
  story, not just a technical footnote.
- The two open data-quality items (missing dates, rider-type anomalies)
  make good material for a "known limitations" section — being upfront
  about what's unresolved is more credible than pretending the data is
  perfect.
- The join-coverage number (4,736 / 4,738 = 99.96%, with a clean
  explanation for the 2 misses) is a good, simple, quotable stat.
---

## Stage 2 – BigQuery Extraction Foundation

### Objective

Build and verify a reusable framework for validating BigQuery source metadata before implementing the ETL pipeline.

### Completed

- Implemented extraction modules for configuration, table ID validation, BigQuery client, and metadata validation.
- Added a command-line validation script.
- Added unit tests covering configuration, table ID validation, BigQuery client, and metadata validation.

### Verified Findings

#### Local unit tests

Command:

```bash
python -m pytest
```

Result:

- 34 tests passed.

#### Live BigQuery validation

Command:

```bash
python scripts/validate_source_metadata.py
```

Results:

**nyu-datasets.citibike.m_daily_trips**

- PASS
- row_count: 4738
- distinct_dates: 4738
- null_dates: 0
- min_date: 2013-06-01
- max_date: 2026-05-31

**nyu-datasets.weather.m_weather_daily_nyc**

- PASS
- row_count: 54912
- distinct_dates: 54912
- null_dates: 0
- min_date: 1876-01-01
- max_date: 2026-05-29

### Engineering Reflections

- Unit tests verified the implementation logic without requiring network access.
- Live validation confirmed authentication, configuration, permissions, and expected BigQuery metadata.
- The reliable project testing command is:

```bash
python -m pytest
```

because the standalone `pytest` command resolved to the Anaconda installation instead of the project's virtual environment.