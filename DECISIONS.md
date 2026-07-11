# Decisions

Architecture Decision Record (ADR) log. Every material decision and every
assumption made in the absence of explicit direction is recorded here,
newest last. This file — not chat history — is the persistent record.

Status values: **Proposed** (needs confirmation) · **Accepted** ·
**Superseded** (link to the replacing entry)

---

### D-001 — Use this GitHub repository as persistent project memory
**Status:** Accepted
**Context:** The project spans many stages and potentially many sessions
with different contributors (human or AI). Chat history is not durable or
shared.
**Decision:** All decisions, task status, and stage progress are recorded
in this repo (`DECISIONS.md`, `TASKS.md`, `PROJECT_PLAN.md`,
`docs/stage_reports/`), not solely in chat.

### D-002 — No GCP project ID or credentials committed
**Status:** Accepted
**Context:** Explicit project requirement.
**Decision:** All GCP configuration (project ID, dataset names, service
account paths) is read from environment variables. `config/.env.example`
documents the expected variables with placeholder values only. Real values
live in a local, gitignored `.env`.

### D-003 — Nine-stage roadmap, each requiring explicit approval
**Status:** Accepted
**Context:** Project requirement to break work into small, reviewable
stages.
**Decision:** Work proceeds through Stages 0–8 as defined in
`PROJECT_PLAN.md`. No stage's code is written before the prior stage is
approved, and no stage writes deliverables that belong to a later stage.

### D-004 — Interpreted historical range: ~2013 to most recent available month
**Status:** Proposed — needs confirmation
**Context:** The request specifies "thirteen years of public Citi Bike trip
data." Citi Bike launched in NYC in 2013.
**Decision (proposed):** Interpret the range as program launch (2013)
through the most recently available month of published data (~2026 at
time of writing). To be confirmed against actual data availability in
Stage 1.
**Alternatives considered:** A fixed trailing 13-year window ending at
project start date — rejected for now since it doesn't align with "public
Citi Bike trip data" as a complete historical dataset, but flagged for
owner confirmation.

### D-005 — Weather table is assumed externally provided
**Status:** Proposed — needs confirmation
**Context:** The technical goal says the pipeline "joins them to a
provided daily weather table," implying the weather data itself is not
extracted by this pipeline.
**Decision (proposed):** Treat the daily weather table as an existing
input (e.g., an existing BigQuery table, or a specified public source like
NOAA) to be identified by the owner, rather than something Stage 2
(Extraction) needs to build. To be confirmed in Stage 1 and finalized in
Stage 6.

### D-006 — Google BigQuery as the target warehouse
**Status:** Accepted
**Context:** Explicit project requirement ("loads the data into
BigQuery").
**Decision:** BigQuery is the warehouse for all standardized trip data,
daily summaries, and the weather join. No alternative warehouse is being
evaluated.

### D-007 — Python for ETL, SQL for transformation models
**Status:** Proposed — needs confirmation
**Context:** Not explicitly specified by the owner. Python + SQL is the
common pattern for BigQuery-based pipelines and matches the folder
structure already proposed (`src/` for Python, `sql/models/` for SQL).
**Decision (proposed):** Use Python for extraction/loading scripts and SQL
for all transformation models. To be confirmed before Stage 2 begins.

### D-008 — No ETL or dashboard code in Stage 0
**Status:** Accepted
**Context:** Explicit instruction for this task.
**Decision:** Stage 0 delivers only documentation, folder structure, and
placeholder/config files. No extraction, transformation, loading, SQL
model, or dashboard code is included.
