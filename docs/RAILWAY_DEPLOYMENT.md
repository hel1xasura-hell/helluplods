# Railway deployment
Do this only after CI is green and you accept the costs. Nothing deploys automatically: use **Actions -> Deploy** (manual, needs `RAILWAY_TOKEN`, a green CI run and, if you configure it, reviewer approval on the `production` environment).

## Services (one repo, five services + two plugins)
| Service | Root directory | Dockerfile | Config file |
|---|---|---|---|
| api | `backend` | `Dockerfile` (runs `alembic upgrade head`, then uvicorn on `$PORT`) | `infrastructure/railway/api.json` |
| worker-default | repo root | `workers/Dockerfile.default` (Celery worker + beat: heartbeat, publishing tick, stale recovery, nightly backup) | `worker-default.json` |
| worker-browser | repo root | `workers/Dockerfile.browser` (Playwright; give it at least 1 GB RAM) | `worker-browser.json` |
| worker-render | repo root | `workers/Dockerfile.render` (FFmpeg; CPU heavy) | `worker-render.json` |
| frontend | `frontend` | `Dockerfile` (set the `VITE_*` build args) | - |
Add **Postgres** and **Redis**, then set `DATABASE_URL` to the plugin's reference (`${{Postgres.DATABASE_URL}}`) and `REDIS_URL` likewise. Railway gives a plain `postgresql://...` URL: that is fine, because the app rewrites it to `postgresql+psycopg://` (psycopg 3, the only PostgreSQL driver installed) before the API, Alembic or any worker uses it. Do not install psycopg2.

## Variables (api and all workers share most of them)
`APP_ENV=production`, `JOB_BACKEND=celery`, `OWNER_EMAIL`, `FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS`, `TOKEN_ENCRYPTION_KEY`, `CORS_ORIGINS` and `FRONTEND_URL` (your https frontend URL),
`S3_*` (required in practice: Railway disks are too small for video), YouTube variables when ready.

## Before every production deploy
`APP_ENV=production ... python scripts/preflight.py` (reads your variables, exits 1 on unsafe settings such as wildcard CORS, http origins, default DB password, bad encryption key).
Then check **Settings -> System health** and **Security Center -> Configuration checks** after the deploy.

## Scaling toward 50 videos a day
Render is the bottleneck: one render worker handles one video at a time (`-c 1`). Add replicas of `worker-render` to raise throughput.
YouTube's quota and your channel's upload limit are the other ceilings; see `docs/YOUTUBE_SETUP.md`.
