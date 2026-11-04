# Backup and recovery

## What is backed up
- **Database**: a nightly `pg_dump` (custom format) is taken by the default worker at 03:15 UTC, verified (must be a valid archive), stored in object storage under
  `<owner>/backups/`, and pruned (newest 14 kept, older than 30 days removed, the newest is never removed). **Settings -> Database backups** can also take one now
  and lists them; failures raise a notification and an audit event.
- **Media** (recordings, renders, screenshots, thumbnails): live in object storage. Turn on bucket **versioning** and, ideally, replication in your storage provider.
  The database only references them.
- **Secrets**: not in backups. Keep `TOKEN_ENCRYPTION_KEY` safe: without it stored YouTube tokens cannot be decrypted (you would just reconnect).

## Restore (practice this once before you need it)
1. Create a scratch database. 2. `DATABASE_URL=postgresql://... ./scripts/restore_db.sh backup.dump` (it validates the file and asks you to type `restore`).
3. Run `alembic upgrade head`. 4. Start the API against it and check the dashboard.
Download a backup from the Settings page's backup list (`GET /api/backups/{id}/download`) or from the bucket.

## Manual backup
`DATABASE_URL=... ./scripts/backup_db.sh` writes `backup-<timestamp>.dump` locally.

## Disaster notes
- Keep a copy of at least one recent dump **outside** your hosting account.
- Stuck renders/uploads/tasks are recovered automatically (marked failed so you can retry; uploads resume).
