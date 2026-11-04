# Companion (desktop)

Runs on Windows, macOS or Linux. Pairs with a one-time code from Security Center, then records tasks locally.

    pip install playwright && playwright install chromium
    python -m companion pair --server https://YOUR-API --code ABCDE-FGH23
    python -m companion run  --server https://YOUR-API

Needs Python 3.12+. The recorder and SSRF guard in `vendor/` are copied from the backend by
`scripts/sync_companion.sh`; re-run it after changing those files. A packaged Electron/Tauri shell around this
agent is not built yet.
