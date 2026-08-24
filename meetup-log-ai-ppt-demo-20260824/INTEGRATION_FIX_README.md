# ML-Backend interface integration

Use the project directories at this root:

- `ml-service`: FastAPI chat analysis and recommendation service
- `backend`: Spring Boot proxy and Flyway migrations
- `frontend`: React frontend

## Windows CMD verification

```cmd
cd ml-service
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
set MEETUP_DB_BACKEND=sqlite
.venv\Scripts\python -m pytest tests -q
```

PowerShell uses `$env:MEETUP_DB_BACKEND="sqlite"` instead of the CMD `set` command.

## Added interface behavior

- `idempotency_key` prevents duplicate message accumulation.
- `state_version` prevents recommendations from stale preference state.
- `preference_deltas` reports structured `UPSERT` and `REMOVE` changes.
- `POST /v1/chat/rooms/{room_id}/recommendations` recommends from the stored full room preference state.
- Flyway migration: `V5__chat_ml_interface.sql` (`V4` is already used by incremental chat analysis).

Validated result: 40 ML tests passed, 3 optional external tests skipped; Spring Boot tests passed.
