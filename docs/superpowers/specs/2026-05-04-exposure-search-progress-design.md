# Exposure Search Progress Design

## Goal

Add live search-progress visibility for exposure-search tasks in both the `AssetMap Discovery` floating window and the task UI, and ensure tasks end automatically once all search queries finish.

## Scope

This change covers:

- backend exposure-search task progress state
- exposure-search API serialization
- floating-window progress display
- task page / task detail progress display
- automatic task completion when all queries are done

This change does not introduce a new task engine or a new database table.

## Source of Truth

Use `ExposureSearchTask.query_plan` as the canonical progress model.

Each query-plan item continues to store:

- `query`
- `status`
- `results_count`

Task-level derived fields will be computed from `query_plan`:

- `current_query`
- `next_query`
- `completed_queries`
- `total_queries`
- `progress_percent`

These values should be exposed by the API response schema, not stored as separate DB columns.

## Backend Design

### Query lifecycle

For each query:

1. mark query `running`
2. derive and expose `current_query`
3. derive and expose `next_query`
4. when done, mark query `completed`
5. update progress counts and percentage

### Completion rule

When every query in `query_plan` is `completed`, `stopped`, or otherwise terminal:

- finalize the task immediately
- set task status to `completed` unless the task was explicitly stopped
- do not leave the task hanging in a manual-wait state

Manual intervention remains valid only for blocked pages. It must not prevent task completion once no query work remains.

### API changes

Extend `ExposureSearchTaskSchema` with derived read-only progress fields:

- `current_query: str | None`
- `next_query: str | None`
- `completed_queries: int`
- `total_queries: int`
- `progress_percent: int`

These fields should be returned by:

- `GET /api/v1/exposure-search/tasks`
- `GET /api/v1/exposure-search/tasks/{task_id}`

## Floating Window Design

The `AssetMap Discovery` window should display:

- a compact progress bar
- completed/total query count
- current query text
- next query text

It should not compute progress locally. It should poll the backend task detail endpoint for the active task and render the returned values.

If there is no active task context, the progress block stays hidden.

## Task UI Design

Task list and task detail should display:

- progress bar
- completed/total query count
- current query
- next query

Progress rendering should use the same backend fields as the floating window to avoid drift.

## Error Handling

- If `query_plan` is empty, progress is `0/0` and `progress_percent = 0`
- If no query is currently running, `current_query = null`
- If there is no remaining pending query, `next_query = null`
- If polling fails in the floating window, keep the rest of the controls usable and show no stale “running” text changes from guessed local state

## Testing

Add or update tests for:

- derived progress fields from mixed query states
- correct `current_query` and `next_query`
- automatic completion when all queries finish
- floating-window script rendering logic for returned progress payload
- task API responses including new progress fields

## Files

Expected touch points:

- `backend/app/services/exposure_search/__init__.py`
- `backend/app/schemas/exposure_search.py`
- `backend/app/api/exposure_search.py`
- `backend/app/services/exposure_search/discovery_script.js`
- relevant frontend task-view files if accessible in this environment
- backend tests for exposure-search runtime and API
