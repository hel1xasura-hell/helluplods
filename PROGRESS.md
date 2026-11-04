# Build progress (read this first when resuming)

Resume rule: when the owner writes "continue", pick up at the first unchecked item below.

## Environment limits seen while building (Stage 1)
The build sandbox had no network: packages could not be installed, so FastAPI/React tests and builds were NOT
run there. Run them in CI (GitHub Actions) or locally; see "Verified" below for what actually ran.

## Stage 1 — foundation
- [x] Monorepo layout, .gitignore, .env.example
- [x] Backend: config, JSON logging, security middleware (headers, rate limit, origin check), crypto helper
- [x] Models for all 25 required entities (UUID ids, FKs, indexes, constraints, timestamps)
- [x] Alembic baseline migration
- [x] Firebase ID-token verification, single-owner initialisation (OWNER_EMAIL), ownership helper, audit events
- [x] SSRF guard, storage interface (local + S3), honest integration status
- [x] Agent runtime (timeout, retries, cancel, progress, logs, tool/secret allow-lists) + registry of 16 agents
- [x] API: health, /api/me, projects CRUD, research targets, dashboard, agents, integrations
- [x] Frontend: PWA shell, dark/light themes, sidebar + mobile bottom nav, login, Overview, Projects,
      AI Research (target intake), AI Agents, Security Center, Settings; honest "not built" pages for the rest
- [x] Docker, compose, CI workflow, Railway notes, tests written
- [x] Docs: ARCHITECTURE, LOCAL_DEVELOPMENT, GITHUB_SETUP, RAILWAY_DEPLOYMENT, FIREBASE_AUTH_SETUP,
      ENVIRONMENT_VARIABLES, DATABASE_SETUP, BACKUP_AND_RECOVERY, SECURITY, API_DOCUMENTATION, USER_GUIDE
- [ ] Push to GitHub and get first green CI run (owner action)

## Stage 2 — research + browser automation (mostly done)
- [x] Safe Playwright capture (SSRF on every request + final URL, downloads/service workers blocked, robots.txt)
- [x] Multi-page exploration: follows same-site feature/pricing/docs links (max 3, polite delay, robots respected)
- [x] Untrusted-content sanitizer + prompt wrapper
- [x] Honest extraction-only reports: features unverified, observed prices unverified, tested_hands_on false,
      Play Store = listing only, name targets -> "needs official URL"
- [x] Failure reason stored on target and shown in UI
- [x] AI provider abstraction (Anthropic via httpx) + optional tutorial-idea suggestions (labelled unverified);
      silently skipped when ANTHROPIC_API_KEY is absent (never fabricated)
- [x] Celery dispatch (JOB_BACKEND=celery -> browser queue); worker heartbeat -> dashboard "cloud workers"
- [x] Notifications API + bell; Browser Lab shows real run history
- [x] Tests written for all of the above
- [x] Pause / resume / stop for runs (DB-backed control flag, honoured between pages, audited); partial report kept on stop
- [x] Progress + current URL per run; WebSocket /ws/runs (token as first message, Origin checked) with polling fallback
- [x] Browser Lab: live status, progress bar, current page, Pause/Resume/Stop
- [x] Claim checks: deterministic text-match across visited pages (labelled; never claims truth)
- [ ] Live screenshot preview in Browser Lab; start-a-session-manually control (runs start from AI Research)
- [ ] Workflow exploration: clicking menus/forms with Playwright (needs care: no auth/paywall/CAPTCHA bypass)
- [ ] Android emulator/device exploration (authorised devices only)
- [ ] First CI run is the real test of everything above (owner action)

## Stage 3 — recording, desktop companion, device pairing (mostly done)
- [x] Real WebM screen recording with Playwright (SSRF + robots checked, downloads blocked, scroll tour,
      timestamped action log for later cursor highlights, ffprobe duration); magic-byte validation of uploads
- [x] Cloud recording task + Recordings page (play, range requests), notifications
- [x] Executor rule: exactly one executor per task (cloud / local / both -> local if a device is online else cloud)
- [x] Device pairing: one-time 10-minute code, hashed; credential shown once, hashed at rest; revoke; throttled pairing
- [x] Device API: heartbeat, atomic task claim (owner-scoped), file upload, complete, fail; revoked devices locked out
- [x] Companion agent (Python, Windows/macOS/Linux): pair, run, record, upload; https enforced except localhost;
      user-only config file; explicit --allow-host opt-in for private hosts
- [x] Security Center: pairing codes, device list (online/offline/revoked), revoke
- [x] CI job for the companion end-to-end test
- [ ] Electron/Tauri packaged shell around the companion (agent is a Python program for now)
- [ ] OS keychain credential storage in the companion (currently a 0600 file)
- [ ] Screen capture beyond the browser (desktop/windows) and local file access
- [ ] Presigned S3 upload for large videos (currently the API receives the whole file, 200 MB cap)
- [ ] Stale-claim recovery (a claimed task whose device vanished is only failed on revoke)
- [ ] Local Playwright research tasks on devices (research always runs in the cloud for now)

## Stage 4 — scripts, voice, video, thumbnails (mostly done)
- [x] Script Studio: scripts/scenes CRUD, reorder, skeleton from research (no invented narration), per-scene footage, trim, zoom
- [x] Subtitles: cues, SRT/VTT/ASS, editable per scene; chapters from the real timeline; metadata + accuracy warnings
- [x] Narration: upload your own audio (validated), Piper (free/offline) + ElevenLabs providers, audio tied to narration text hash
- [x] FFmpeg render: real footage + narration, 16:9/9:16/1:1, fps, intro/outro cards, cursor highlight, zoom, fades,
      loudness normalisation, soft or burned-in subtitles, optional music mix, progress, cancel
- [x] Quality checks: streams, resolution, duration drift, real footage, narration, subtitles, loudness
- [x] Thumbnail Studio: 3 templates, real screenshot background, editable text, accent, badge, select, export PNG
- [x] AI script drafting (needs key; labelled draft; untrusted-data wrapping)
- [x] Frontend: Script Studio, Video Studio (render, QC, preview, download), Thumbnail Studio
- [ ] Approved background-music library UI (renderer supports a music file; no upload/approval screen yet)
- [ ] Multi-language voices UI (language field exists on scripts; voice/model choice per language not built)
- [ ] Editing templates/branding presets (settings are per render; no saved presets); logo upload
- [ ] Footage replace/trim preview in the editor (currently pick recording + start time + zoom)
- [ ] AI thumbnail concepts and AI SEO drafts (metadata is manual + deterministic checks)
- [ ] Media Library page (files exist, no unified browser yet)
- [ ] Approvals row creation after a passing render (Stage 5)

## Stage 5 — YouTube, uploads, scheduling, approvals (mostly done)
- [x] OAuth with PKCE + encrypted expiring state; least-privilege scopes; encrypted refresh token; disconnect/revoke
- [x] Resumable upload with chunking, retry/backoff on retriable errors, saved session, resume after failure, duplicate-upload protection
- [x] Quota accounting (Pacific-day reset), configurable cost/limit, channel upload-limit message, thumbnail upload (non-fatal)
- [x] Approval workflow (pending/approved/rejected), explicit kids + AI-disclosure answers, forced AI disclosure when an AI voice was used
- [x] Scheduling via private + publishAt; automatic mode with strict policy, daily limit, publish hours, fallback to human review
- [x] Repetitive-content guard (duplicate title), metadata checks (< > forbidden, accuracy warnings), chapters
- [x] Frontend: Approvals, Publishing (connect, quota, defaults, uploads, retry/cancel)
- [x] docs/YOUTUBE_SETUP.md with the verified restrictions (audit-gated public uploads, quota, testing-mode token expiry)
- [ ] Real end-to-end test against YouTube (needs credentials; also the compliance audit before public uploads)
- [ ] Upload from storage without loading the whole file in memory (fine up to ~hundreds of MB)
- [ ] Publishing calendar as a visual calendar (currently a sorted list)
- [ ] Analytics pull from YouTube (Stage 6)

## Stage 6 — analytics, security, notifications, deployment, monitoring, backups (built)
- [x] Production analytics from real records (renders/uploads per day, success rates, avg render time, approval funnel, most-flagged checks, progress toward 50/day)
- [x] YouTube statistics sync (views/likes/comments; 1 quota unit per 50 videos) + Analytics page with accessible SVG charts
- [x] System health (DB, Redis, storage, FFmpeg, Chromium, pg_dump, workers, queue depth, stuck work) + stale-work recovery (API + every 5 min)
- [x] Nightly verified `pg_dump` backups with retention, manual backup, download, restore script; failures notify + audit
- [x] Security Center: live configuration checks, filterable audit trail, paired computers
- [x] Notifications (bell) for research, recordings, renders, approvals, uploads, backups, recovery
- [x] Deployment: manual gated Deploy workflow (needs green CI + token), per-service Railway configs, production preflight script
- [x] Full-journey API test (login -> project -> research -> record -> script -> thumbnail -> render -> approve -> upload -> analytics)
- [x] Frontend component tests (login, forms, approvals gating, overview, chart)
- [ ] Email/push notifications (in-app only)
- [ ] Redis-backed rate limiting (in-memory; fine for one API instance)
- [ ] Visual regression/responsive tests in a real browser (Playwright UI e2e against the built frontend)
- [ ] Restore drill performed on a real database (script exists; never run)

## Overall status (end of the build session)
All six stages are implemented. Honest limits:
1. **Most automated tests have never run.** Only the dependency-free suites ran here (media 13, YouTube logic 10, ops 6, plus real-browser/FFmpeg/companion
   experiments). The FastAPI, SQLAlchemy and React tests need packages that could not be installed offline. Expect CI to find bugs.
2. **Nothing has touched real external services**: Firebase, Claude, Piper/ElevenLabs, S3, YouTube, Railway.
3. **YouTube gates**: public/unlisted uploads need Google's API compliance audit; default quota allows about 6 uploads a day (see docs/YOUTUBE_SETUP.md).
4. **Not built / partial** (from the original spec): Android emulator/device exploration, Electron/Tauri packaging, clicking through menus/forms during research,
   approved-music library UI, saved branding templates, multi-language voice selection, AI thumbnail concepts and AI SEO drafts, visual calendar.

## Suggested next steps
1. Push to GitHub, run CI, fix failures (paste the failing logs to Claude and say "continue").
2. Create Firebase, then deploy to Railway with `JOB_BACKEND=celery` and S3-compatible storage; run `scripts/preflight.py`.
3. Run the whole journey on a private test project with approval mode and private uploads; apply for the YouTube audit.

## Verified in the build sandbox
- Frontend runtime smoke test: all 16 pages plus the app shell were transpiled with tsc and server-rendered with React 19 against realistic fixture data
  (router, icon and Firebase libraries stubbed; API stubbed). No crashes; expected content present. Not covered: effects, clicks, real network, styling.
- Static scans of all Python (undefined names, unused imports, unused locals) are clean; frontend scan for unused/undeclared identifiers is clean.
  These scans found and fixed unused imports that would have failed the CI lint step, and a NOT NULL bug when clearing scene options.
- Stage 6: ops logic (security checks, retention, staleness, analytics maths) and the production preflight script executed (6 tests via shim + a real preflight run).
  Database-backed Stage 6 tests, the E2E journey test and the frontend component tests are written but NOT run.
- Stage 5: pure YouTube logic executed (10 tests via shim): PKCE/state tamper+expiry rejection, least-privilege scopes, quota math, chunk planning,
  request-body rules, full policy matrix, publish-slot selection. FastAPI-level tests (test_stage5_api.py, fake YouTube client) are written but NOT run.
  Facts checked online: Google states unaudited API projects' uploads are restricted to private; official reference lists 1600 quota units per upload.
- Stage 4: REAL FFmpeg renders from a real Chromium recording in 16:9, 9:16 and 1:1; frames inspected visually (subtitle size/position bug found
  and fixed by switching to ASS at output resolution; cursor highlight and zoom confirmed); quality checks flagged the footage-less scene;
  loudness measured -15.9 LUFS; cancel works. 13 media tests passed via a pytest shim. Thumbnails inspected visually over plain and bright backgrounds.
  FastAPI-level Stage 4 tests (test_stage4_api.py) are written but NOT run.
- Stage 3: REAL Chromium recording produced a valid WebM (ffprobe 8.76 s), blocked an internal-IP request, obeyed robots.txt.
  REAL companion end-to-end against a stub API: wrong code rejected, pair, record, upload, complete; blocked IP -> reported as
  failed; revoked device stops; config file is user-only. Backend device/recording pytest tests are written but NOT run.
- Stage 2: REAL Chromium capture ran against a local test site: extracted title/headings/nav, took a PNG screenshot,
  blocked an internal-IP image request, refused localhost under the strict validator, obeyed robots.txt Disallow,
  flagged an injection string. pytest/FastAPI tests still NOT run (packages unavailable offline).
- Stage 2c: REAL explore_site stop hook ran: stopped after 2 of 4 pages; claim checker returned expected statuses.
- Stage 2b: REAL multi-page exploration ran: visited /pricing and /features, skipped off-site link, recorded a
  robots-disallowed link as blocked instead of fetching it.
- SSRF guard: executed against 9 hostile URLs, all blocked; public IP allowed.
- Agent runtime: executed retry, timeout, permission denial, cancellation, bad input.
- All backend Python compiles; docker-compose and CI YAML parse.
- Frontend: no TypeScript syntax errors. Full typecheck/tests/build NOT run (no packages).
