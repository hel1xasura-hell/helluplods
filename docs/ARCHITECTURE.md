# Architecture

```
Browser / phone (React PWA) --HTTPS+Bearer--> FastAPI (api) --> PostgreSQL
Desktop companion (Python) --HTTPS+Device cred--^     |--> Redis (queues, heartbeats)
                                                      |--> Object storage (S3-compatible; local disk in dev)
Celery workers:  default (publishing, maintenance, beat) | browser (Playwright) | render (FFmpeg)
External: Firebase Auth, Claude API (optional), Piper/ElevenLabs (optional), YouTube Data API
```

## Modules (backend/app)
| Area | Where | What it does |
|---|---|---|
| Auth | `auth/`, `core/middleware.py` | Firebase ID-token verification; the verified email must equal `OWNER_EMAIL`; uid is pinned on first login; rate limit, security headers, Origin check |
| Research | `browser/safe_browser.py`, `services/research.py` | SSRF-checked Playwright capture and exploration, robots.txt, untrusted-content sanitising; honest extraction-only reports |
| Recording | `browser/recorder.py`, `services/recording.py`, `api/routes/devices.py` | Real WebM recordings in the cloud or on a paired computer; exactly one executor per task |
| Script/Video | `media/`, `services/render_service.py` | Scenes, subtitles (SRT/VTT/ASS), narration (upload / Piper / ElevenLabs), FFmpeg render, quality checks, thumbnails |
| Publishing | `integrations/youtube_*.py`, `services/publishing.py` | OAuth+PKCE, approvals, resumable uploads, quota, duplicate protection, automatic-mode policy |
| Operations | `services/ops.py`, `services/maintenance.py`, `api/routes/ops.py` | Health, stale-work recovery, backups, audit, security checks |
| Agents | `agents/` | Typed agent runtime (timeout, retries, cancel, tool/secret allow-lists) and the 16 agent definitions |

## Principles
- **Single owner.** There is no sign-up path; every query is scoped to the owner (`get_owned_project` and joins on `Project.owner_id`).
- **Honesty.** Unbuilt agents say so; missing credentials show as status; reports never claim hands-on testing they did not do; recordings are real captures; text cards are labelled as such.
- **Safety by default.** Uploads default to private; automatic publishing must pass a strict policy or the video waits for approval; AI disclosure is forced when an AI voice is used.
- **Isolation.** Heavy browser and render work run in separate worker images and queues, never in the web process.
- **Recoverability.** Resumable uploads, stale-work recovery every 5 minutes, nightly backups with retention, idempotent upload jobs.

## Status by stage: see PROGRESS.md.
