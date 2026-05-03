# Repository Guidelines

## Project Structure & Module Organization
`backend/` contains the FastAPI application, tests, and Python dependencies. Main code lives under `backend/app/` with `api/`, `core/`, `models/`, `schemas/`, `services/`, and `tasks/` separated by responsibility. `backend/tests/` holds pytest coverage for API, task, and service behavior. `main.py` starts the backend from the repo root, `backend/init_db.py` initializes the database, and `frontend/` contains the Vue 3 + Vite admin UI described in `README.md`. Runtime outputs such as `results/`, `screenshots/`, `logs/`, and `report/` should be treated as generated artifacts, not source.

## Build, Test, and Development Commands
Install backend dependencies with `python -m pip install -r backend/requirements.txt`. Initialize the database with `python backend/init_db.py`. Run the API locally from the repo root with `python main.py`. Run backend tests with `python -m pytest backend/tests` or narrow scope, for example `pytest backend/tests/test_reports.py -q`. For the frontend, use `npm install`, `npm run dev`, and `npm run build` inside `frontend/`.

## Coding Style & Naming Conventions
Follow existing Python conventions: 4-space indentation, `snake_case` for functions/modules, `PascalCase` for classes, and explicit typing where the surrounding code uses Pydantic or SQLAlchemy models. Keep FastAPI route handlers thin and push logic into `services/` or `tasks/`. Name tests `test_<feature>.py` and keep fixtures or helpers close to the test module they support. Preserve existing API versioning and path patterns under `backend/app/api/`.

## Testing Guidelines
Pytest is configured by `backend/pytest.ini` with `backend/tests` as the test root. Add or update tests with every backend behavior change, especially for collectors, report generation, and job-processing flows. Prefer targeted runs while iterating, then finish with `python -m pytest backend/tests`. If a change touches the frontend build or API contracts, verify the frontend still builds cleanly.

## Commit & Pull Request Guidelines
Recent history uses short conventional prefixes such as `feat:`, `fix:`, and `chore:`; keep that pattern and write imperative summaries, for example `fix: preserve report download filenames`. Keep commits focused on one concern. Pull requests should describe the user-visible impact, list verification steps, link related issues, and include screenshots for UI changes. Call out database, config, or background-task implications explicitly.

## Security & Configuration Tips
Do not commit real API credentials, database secrets, or generated runtime data. Frontend API base URL settings belong in `frontend/.env.*`; backend configuration should stay environment-driven. Review temporary SQLite files and upload samples before committing to avoid leaking local state.
