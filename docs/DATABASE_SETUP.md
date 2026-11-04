# Database
PostgreSQL 16. Schema is in `backend/app/models`. `alembic upgrade head` applies migrations (the api container does it
on start). The baseline migration `0001` builds the schema from the models; create later changes with
`alembic revision --autogenerate -m "message"` and review them before committing. Tests use in-memory SQLite;
CI additionally runs `upgrade head` and `downgrade base` against real Postgres.
