# Security
Implemented in Stage 1: Firebase ID-token verification on every private route; single owner via `OWNER_EMAIL` + verified
email + uid pinning; ownership-scoped queries; audit events; per-IP rate limiting (in-memory); security headers;
Origin check on state-changing requests (auth is Bearer-only, never cookies, so classic CSRF does not apply);
SSRF guard for submitted URLs (blocks non-http(s), embedded credentials, localhost, private/link-local/reserved
and IPv4-mapped addresses, and resolves DNS); storage key traversal protection; Fernet helper for OAuth tokens;
no secrets in code; React escapes output (no `dangerouslySetInnerHTML`).
Stage 2 adds: every browser request and the final URL are SSRF-checked; downloads and service workers are blocked; robots.txt
is obeyed; page text is sanitised, flagged for injection phrases and never treated as instructions.
WebSocket: token is sent as the first message (not in the URL), Origin is checked, runs are scoped to the owner.
Devices: pairing codes are random, single-use, expire after 10 minutes and are stored hashed; pairing attempts are throttled;
device credentials are random, shown once, stored hashed and revocable (revoking also fails its claimed tasks); a device can
only see and finish tasks of its own owner and cannot use owner endpoints. Uploads are size-capped and checked by magic bytes.
The companion refuses plain-http servers (except localhost) and applies the same SSRF guard as the cloud.
Stage 4: uploaded narration is size-capped (50 MB), checked by magic bytes and probed by FFmpeg before it is stored; render settings
are validated server-side (ratio, size, fps, colours); FFmpeg is run with an argument list (never a shell) and subtitle/title
text goes through files, not command-line escaping; a scene can only use recordings from its own project; narration audio is
never reused after the text changes; AI output is treated as a draft and AI prompts wrap research data as untrusted.
Stage 5: OAuth uses PKCE and an authenticated-encrypted, expiring state (the callback has no bearer header, so the state proves who started it); only the
upload and read-only scopes are requested; refresh tokens are encrypted at rest and removed on disconnect (also revoked at Google, best effort);
uploads are idempotent per render and channel, resume from a saved session instead of restarting, and never upload a second copy once a video id
exists; automatic mode must pass a strict policy (real footage, narration, accurate metadata, explicit kids/AI-disclosure answers, daily limit,
no repeated title) or the video waits for human approval.
Stage 6: `scripts/preflight.py` refuses unsafe production settings; Security Center shows live configuration checks and a filterable audit trail;
backups are verified, retained and downloadable only by the owner; stale work is recovered automatically; deployment is manual and gated on green CI.
Known gaps: DNS-rebinding between check and connect, download scanning, device pairing, Redis-backed rate limits.
