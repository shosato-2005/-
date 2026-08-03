# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A prototype scholarship recommendation tool for Osaka Kyoiku University (大阪教育大学) students. A user enters their profile (residence, faculty/major, grade, parental income, GPA); the app scores every scholarship in a local JSON database against that profile and returns every scholarship as a 1–5 star ranking, sorted best-first.

## Commands

Run from `backend/`:

```bash
# Install dependencies (project root)
pip install -r ../requirements.txt

# Launch the Streamlit app
python -m streamlit run app.py
```

`streamlit` is not reliably on PATH in this environment — always invoke it via `python -m streamlit`, not the bare `streamlit` command.

```bash
# Run the non-UI scoring/recommendation logic standalone (prints JSON to stdout)
python demo.py
```

If console output looks garbled, force UTF-8: `PYTHONIOENCODING=utf-8 python demo.py`.

```bash
# Run the test suite (from the project root, not backend/)
pip install -r requirements-dev.txt
pytest
```

Tests live in `backend/tests/` and cover `models.py`/`scoring.py`/`recommend.py` only (core matching/scoring logic — no Streamlit UI tests). `pytest.ini` at the project root sets `pythonpath = backend` so the tests can use the same flat unqualified imports (`from models import ...`) as the app code, without needing `backend/` as the working directory.

There is no linter configured yet.

## Architecture

All code lives in `backend/` and is a flat set of modules imported by unqualified name (`from models import ...`), so scripts must be run with `backend/` as the working directory / on `sys.path` — this is why `app.py` and `demo.py` both live next to `models.py` rather than in a separate `frontend/` or top-level script.

Data flow: `data/scholarships_sample.json` → `models.Scholarship.from_dict` → `scoring.calculate_score` → `recommend.recommend` → consumed by `app.py` (Streamlit UI) or `demo.py` (CLI).

- **`models.py`** — dataclasses only, no logic (plus one small regex helper). `UserProfile` (residence, faculty, grade, parent_income, gpa, major, field_tags, school_type). `ScholarshipConditions` holds the eligibility rules for one scholarship; **`None`/empty on any condition field means "no restriction," not "excluded."** `Scholarship.from_dict` parses a raw JSON record (including the `"YYYY-MM-DD"` deadline string) into a `Scholarship`. `Scholarship.amount`, `.deadline`, and `.url` are all `Optional` — real scholarship listings frequently have TBD amounts, rolling/unpublished deadlines, or no application page yet, and `from_dict` accepts `null`/missing values for these without erroring (`None` in, `None` out). `deadline_note` and `description` are read straight from the JSON as free text (`description` bundles application method / combinability / eligibility / schedule / recipient count into one human-written paragraph per scholarship, using inline `【ラベル】` markers). `num_recipients`, `application_method`, and `combinability_note` are *not* separate JSON keys — `_extract_section()` pulls them out of `description` by matching its `【支給人数】`/`【申込方法】`/`【併用可否】` markers via regex; if a record's `description` doesn't follow that pattern (or is missing, as for a couple of records not yet covered by the latest data pass), these come back `None` and the UI just falls back to showing the raw `description` text.
- **`majors.py`** — static `MAJORS` list of the university's official 専攻-コース names (used to populate the Streamlit selectbox), plus `MAJOR_TO_FACULTY` (every major maps to "教育学部" — Osaka Kyoiku University has only one faculty) and `MAJOR_TO_FIELD` (major → field tags like `["理系"]`/`["文系"]`/`["体育系"]`/`["芸術系"]`, a judgment call documented in-file). `app.py` derives `UserProfile.faculty` and `UserProfile.field_tags` from these instead of asking the user directly.
- **`scoring.py`** — the scoring rules. Eight criteria (grade, school_type, faculty, major, field_tags, residence, income, gpa) are each worth `WEIGHT_PER_CRITERION = 5`, for a 40-point max (`MAX_SCORE`). Each criterion has a `_match_*` predicate in the `CRITERIA` list — add new scoring factors here (predicate + Japanese label) and mirror the field in `ScholarshipConditions`. `major` matching is exact-membership against `conditions.majors`; `field_tags` matching is "any tag overlaps" against `conditions.field_tags`. `score_to_stars` maps the total to 1–5 stars via fixed thresholds (35/30/25/20).
- **`recommend.py`** — orchestration: loads scholarships from JSON, scores each against a `UserProfile`, sorts by score descending (deadline ascending as tiebreak; scholarships with an unknown deadline sort after ones with a known deadline, within the same score, since `None` can't be compared to a `date`), returns the formatted list, optionally truncated to `top_n` (default `None` — no limit, returns every scholarship). `_format_result` is the only place that shapes the public output dict (`scholarship_id`, `name`, `amount`, `deadline`, `deadline_note`, `stars`, `deductions`, `url`, `description`, `num_recipients`, `application_method`, `combinability_note`); the optional fields pass through as `None` when unknown; `deductions` is populated only when `stars <= 4`.
- **`app.py`** — Streamlit frontend, styled after the "Industry" design system (see `backend/static/`). Two screens driven by `st.session_state["screen"]` (`"list"` or `"detail"`): the list screen renders the sidebar profile form + combinability/application-method filters (unchanged logic from before the redesign) and a 3-per-row grid of result cards; the detail screen (`_render_detail_screen`) shows one scholarship's full description, an eligibility bullet list derived from its real `ScholarshipConditions` (`_conditions_bullets`), and the apply link. Cards are rendered as raw HTML (`unsafe_allow_html=True`) wrapped in an `<a href="?sid=...">` so the *whole card* is clickable; `main()` reads `st.query_params["sid"]` on each rerun to switch screens, then clears it. `_render_result` was replaced by `_render_result_card` (compact list card) and `_render_detail_screen` (full detail) — both build HTML from the same `_format_result` dict `recommend()` already produced, so no scoring/filtering/sorting logic changed. `_tags_html` renders combinability/application-method categories as `.tag` pills; `_conditions_bullets` reads a `Scholarship.conditions` object directly (looked up from the already-loaded list by `id`) rather than adding fields to `recommend.py`'s output contract.
- **`backend/static/`** — `industry-styles.css` (ported verbatim from the `design_handoff_scholarship_search` handoff — tokens + component classes for the "Industry" blueprint-card look) and `streamlit-overrides.css` (maps Streamlit's native widget internals — `data-testid`/`data-baseweb` selectors — onto those same tokens; brittle across Streamlit versions by nature, approximate rather than pixel-perfect for native form widgets). Both are read and injected once per run via `_inject_industry_css()`.
- **`data/scholarships_sample.json`** — real scholarship data collected for Osaka Kyoiku University students (52 records). Schema mirrors `Scholarship`/`ScholarshipConditions` field names exactly, plus `deadline_note`/`description` (see `models.py` notes above). Many entries have `amount` and/or `url` set to `null` where that information isn't published yet — this is expected, not a data-entry error. One record (`S025`) predates the `deadline_note`/`description` data pass and simply omits those two keys — `from_dict`/`_render_result` treat a missing key the same as `null`.

## Hard constraints (do not relax without explicit user instruction)

- **No persistence of user profile data.** Parental income, GPA, and the rest of `UserProfile` must stay in-memory (Streamlit session/local variables) only — never written to disk, logs, or a database.
- **No web scraping or external API calls.** The scholarship database is a static local JSON file for now; do not add network calls to fetch or enrich scholarship data until the user explicitly says this constraint has changed.
- **`school_type` is hardcoded** to `models.DEFAULT_SCHOOL_TYPE` ("国立大学", matching the scholarship data's convention) for this single-university prototype. When generalizing beyond Osaka Kyoiku University, this default needs to be removed and the field made a required, user-supplied input everywhere it's currently defaulted.
