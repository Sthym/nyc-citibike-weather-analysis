# CLAUDE.md — Working Agreement for AI Agents in This Repository

This file tells any AI agent (Claude or otherwise) working in this
repository how to operate. Read this in full before making any change.
Human contributors should follow the same rules.

## Project context

See `README.md` for the business question/goal and `PROJECT_PLAN.md` for
the staged roadmap. This is a public-data engineering project: 13 years of
Citi Bike trip data → standardized → BigQuery → daily summaries → weather
join → public dashboard.

## Core rules

1. **Never hardcode a Google Cloud project ID.** Always read it from an
   environment variable (`GCP_PROJECT_ID`, see `config/.env.example`) or a
   gitignored local config file. This applies to code, SQL, notebooks, and
   docs alike — use a placeholder or variable reference everywhere.
2. **Never create, commit, or push credentials.** No service-account keys,
   API keys, OAuth tokens, or `.env` files with real values. Only
   `config/.env.example` (placeholders only) is committed.
3. **Never commit, push, or merge without explicit approval.** Always
   summarize proposed changes and wait for the repository owner to approve
   before running any Git operation that changes the remote or history.
4. **Treat this GitHub repository as the project's persistent memory.**
   Material decisions go in `DECISIONS.md`. Task status lives in
   `TASKS.md`. Do not rely on chat history as the source of truth — if it
   isn't written down in the repo, it didn't happen.
5. **Work in small, reviewable stages**, as defined in `PROJECT_PLAN.md`.
   Do not jump ahead — e.g., do not write dashboard code while working on
   the extraction stage, even if it seems efficient.
6. **Every stage needs met, verified acceptance criteria** before it is
   marked done in `TASKS.md`. Cite evidence (row counts, test output, a
   note in `docs/stage_reports/`) rather than marking a task complete on
   good faith.
7. **Label every assumption explicitly.** When a requirement is ambiguous
   or a source hasn't been confirmed, add an entry to `DECISIONS.md` marked
   "Proposed — needs confirmation," or an inline `# ASSUMPTION:` comment in
   code, and flag it to the owner.
8. **Any data-affecting change needs data-quality checks.** Extraction,
   transformation, and loading changes must include or update checks for:
   row counts, date completeness, duplicates, missing values, invalid trip
   durations, and weather-join integrity (see `tests/data_quality/`).

## Folder conventions

New files belong in the folder matching their stage — see the table in
`README.md`. Do not introduce a new top-level folder without first
proposing it (name + purpose) to the owner.

## Workflow for a new stage or task

1. Read the stage definition in `PROJECT_PLAN.md` and any relevant open
   items in `TASKS.md`.
2. Draft the change.
3. Summarize the proposed change (files touched, what changed, why) for
   the repository owner.
4. Wait for explicit approval.
5. Only after approval: commit with a message referencing the stage,
   update `TASKS.md`, and log any material decision in `DECISIONS.md`.

## Style conventions (to be confirmed — see DECISIONS.md D-007)

- Python: PEP 8, type hints on function signatures, docstrings on public
  functions.
- SQL: lowercase keywords, one clause per line, explicit column lists
  (avoid `SELECT *` in committed models).
- Markdown docs: one topic per file: don't duplicate content, cross-link
  with relative paths instead.
