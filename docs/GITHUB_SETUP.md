# GitHub setup (phone-friendly)
1. Create a **private** repository `hell-uploads` and upload the repo contents (web UI "Add file -> Upload files", or push from a computer).
2. **Actions -> CI** runs: backend lint + tests (with FFmpeg), Postgres migration up/down, frontend typecheck/tests/build, and the companion end-to-end test with real Chromium.
   Fix anything red first. This is the first real run of most tests, so expect to fix a few things.
3. Never commit `.env`. Put secrets in Railway variables; put `RAILWAY_TOKEN` in GitHub **Settings -> Secrets and variables -> Actions**.
4. Optional but recommended: **Settings -> Environments -> production -> Required reviewers** so the Deploy workflow needs your approval.
5. Deploy only through **Actions -> Deploy** (manual; refuses if CI hasn't passed for that commit).
