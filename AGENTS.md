# Repository Guidelines

## Project Structure & Module Organization
`backend/` contains the FastAPI application, dependencies, and tests. Core backend code lives in `backend/app/` and is split by responsibility into `api/`, `core/`, `models/`, `schemas/`, `services/`, and `tasks/`. Tests live in `backend/tests/`. The repo entry point is `main.py`, and `backend/init_db.py` initializes the database. `frontend/` contains the Vue 3 + Vite admin UI. Treat `results/`, `screenshots/`, `logs/`, and `report/` as generated artifacts, not source.

## Build, Test, and Development Commands
Install backend dependencies with `python -m pip install -r backend/requirements.txt`. Initialize local state with `python backend/init_db.py`. Run the API from the repo root with `python main.py`. Run all backend tests with `python -m pytest backend/tests`; use targeted runs while iterating, for example `pytest backend/tests/test_reports.py -q`. In `frontend/`, use `npm install`, `npm run dev`, and `npm run build`.

## Coding Style & Naming Conventions
Use 4-space indentation in Python. Follow existing naming patterns: `snake_case` for functions and modules, `PascalCase` for classes, and explicit typing where Pydantic or SQLAlchemy models already use it. Keep FastAPI route handlers thin and move business logic into `services/` or `tasks/`. Preserve existing API versioning and route patterns under `backend/app/api/`.

## Testing Guidelines
Pytest is configured through `backend/pytest.ini` with `backend/tests` as the test root. Name test files `test_<feature>.py`. Add or update tests with every backend behavior change, especially around collectors, report generation, and job-processing flows. Finish backend work with a full `python -m pytest backend/tests` run. If API contracts or UI behavior change, also verify `npm run build` in `frontend/`.

## Commit & Pull Request Guidelines
Follow the existing conventional prefixes such as `feat:`, `fix:`, and `chore:` with short imperative summaries, for example `fix: preserve report download filenames`. Keep commits focused on one concern. Pull requests should explain user-visible impact, list verification steps, link related issues, and include screenshots for UI changes. Call out database, config, or background-task implications explicitly.

## Security & Configuration Tips
Do not commit real credentials, local database secrets, or generated runtime data. Keep frontend API base URLs in `frontend/.env.*` and backend configuration environment-driven. Review SQLite files, uploads, and sample data before committing to avoid leaking local state.
