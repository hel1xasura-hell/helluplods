# API
Interactive docs at `/docs` outside production. All `/api/*` routes need `Authorization: Bearer <Firebase ID token>`.
- `GET /health/live`, `GET /health/ready`
- `GET /api/me`
- `GET|POST /api/projects`, `GET|DELETE /api/projects/{id}`
- `GET|POST /api/projects/{id}/targets`
- `GET /api/dashboard`, `GET /api/agents`, `GET /api/integrations`
- `POST /api/targets/{id}/research` (202; runs in background), `GET /api/targets/{id}/report`, `GET /api/screenshots/{id}`
- `GET /api/runs` recent agent runs; `GET /api/notifications`, `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`
- `POST /api/runs/{id}/pause|resume|stop` (acts between pages); WebSocket `/ws/runs` (send `{"token": "<ID token>"}` as the first message)
- Recording: `POST /api/targets/{id}/record`, `GET /api/recordings`, `GET /api/recordings/{id}/file` (Range supported), `GET /api/recording-tasks`
- Devices (owner): `POST /api/devices/pairing-codes`, `GET /api/devices`, `DELETE /api/devices/{id}`
- Devices (no credential yet): `POST /api/devices/pair` with the one-time code
- Devices (header `Authorization: Device <credential>`): `POST /api/device/heartbeat`, `POST /api/device/tasks/claim`,
  `PUT /api/device/tasks/{id}/file`, `POST /api/device/tasks/{id}/complete`, `POST /api/device/tasks/{id}/fail`
- Scripts: `GET|POST /api/projects/{id}/scripts`, `GET|PATCH|DELETE /api/scripts/{id}`, `POST /api/scripts/{id}/scenes`,
  `PATCH|DELETE /api/scenes/{id}`, `POST /api/scripts/{id}/scenes/reorder`, `POST /api/scripts/{id}/generate-ai?target_id=` (needs ANTHROPIC_API_KEY)
- Subtitles/metadata: `GET /api/scripts/{id}/subtitles.srt|vtt`, `GET|PUT /api/scripts/{id}/metadata` (chapters + accuracy warnings)
- Narration: `PUT /api/scenes/{id}/audio` (raw audio body), `GET /api/scenes/{id}/audio`, `GET /api/voices`, `POST /api/scripts/{id}/voice` (`piper` or `elevenlabs`)
- Rendering: `POST /api/scripts/{id}/render`, `GET /api/renders`, `GET /api/renders/{id}`, `POST /api/renders/{id}/cancel`,
  `GET /api/renders/{id}/file` (Range), `GET /api/renders/{id}/subtitles.srt|vtt`
- Thumbnails: `GET /api/thumbnail-templates`, `GET|POST /api/projects/{id}/thumbnails`, `GET /api/thumbnails/{id}/file?download=true`,
  `POST /api/thumbnails/{id}/select`, `DELETE /api/thumbnails/{id}`; `GET /api/projects/{id}/screenshots`
- YouTube: `GET /api/youtube/status`, `POST /api/youtube/oauth/start`, `GET /api/youtube/oauth/callback` (browser redirect, identity from encrypted state),
  `DELETE /api/youtube/accounts/{id}` (removes our stored token only)
- Publishing: `GET|PUT /api/publishing/defaults`, `GET /api/approvals`, `POST /api/approvals/{id}/approve|reject`,
  `GET /api/uploads`, `POST /api/uploads/{id}/retry|cancel`, `GET /api/publishing/calendar`
- Operations: `GET /api/system/health`, `POST /api/system/recover`, `GET /api/security/checks`, `GET /api/audit?action=&before=`,
  `GET|POST /api/backups`, `GET /api/backups/{id}/download`
- Analytics: `GET /api/analytics/production?days=`, `GET /api/analytics/youtube`, `POST /api/analytics/youtube/sync`
