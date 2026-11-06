# Environment variables
See `.env.example` for the full list with comments.

| Variable | Required | Purpose |
|---|---|---|
| DATABASE_URL, REDIS_URL | yes | Postgres and Redis. `postgresql://` and `postgres://` are accepted and rewritten to `postgresql+psycopg://` |
| OWNER_EMAIL | yes | Only this verified Firebase email can use the app |
| FIREBASE_PROJECT_ID | yes | Verify ID tokens |
| FIREBASE_CREDENTIALS | no | Enables revocation checks |
| CORS_ORIGINS | yes | Allowed frontend origins (comma separated) |
| JOB_BACKEND | no | `inprocess` (default) or `celery` to run research on the browser worker |
| PIPER_BINARY, PIPER_MODEL | no | Free offline narration (Piper). Absent -> upload your own audio |
| ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID | no | Paid narration provider |
| YOUTUBE_CLIENT_ID/SECRET/REDIRECT_URI, FRONTEND_URL | for YouTube | OAuth client; redirect URI must match Google Cloud exactly |
| YOUTUBE_DAILY_QUOTA, YOUTUBE_UPLOAD_COST | no | Quota accounting (defaults 10000 and 1600); confirm in Cloud Console |
| TOKEN_ENCRYPTION_KEY | for YouTube | Fernet key encrypting OAuth tokens |
| ANTHROPIC_API_KEY | later | Claude provider; absent → AI agents report not configured |
| S3_* | production | Object storage; absent → local disk |
| YOUTUBE_CLIENT_ID/SECRET | later | YouTube OAuth |
| VITE_* | frontend build | API URL and Firebase web config |
