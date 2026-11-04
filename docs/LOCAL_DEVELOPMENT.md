# Local development
1. `cp .env.example .env` and fill `OWNER_EMAIL`, `FIREBASE_PROJECT_ID`.
2. `docker compose up -d postgres redis`.
3. Backend: `cd backend && pip install -r requirements-dev.txt && alembic upgrade head && uvicorn app.main:app --reload`.
4. Frontend: `cd frontend && cp .env.example .env && npm install && npm run dev`.
5. Tests: `pytest -q` (backend, uses in-memory SQLite) and `npm test` (frontend).
6. Everything in containers: `docker compose up --build`.
7. Companion test (real Chromium): `pip install playwright pytest && playwright install chromium && pytest desktop/tests`.
   After editing `backend/app/browser/recorder.py` or `services/ssrf.py`, run `scripts/sync_companion.sh`.
