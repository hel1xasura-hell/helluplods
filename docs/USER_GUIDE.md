# User guide (Stage 1)
1. Sign in with the owner account.
2. **Projects → New project.** Choose where browsers run and whether uploads need your approval.
3. **AI Research.** Pick the project and add websites, app names or Play Store URLs. They are saved; automated research
   starts in Stage 2.
4. **Settings** shows which integrations still need credentials.
Sections marked "Not built yet" will appear in later stages.

## Recording and your own computer (Stage 3)
1. **AI Research → Record** on a website target. Where it runs follows the project's setting: Cloud, Local computer, or Both
   (Both uses your computer when it is online, otherwise the cloud, never both).
2. To use your computer: **Security Center → New pairing code**, then on that computer run the companion (see
   `desktop/companion/README.md`): `python -m companion pair --server https://YOUR-API --code ABCDE-FGH23`, then `python -m companion run --server ...`.
3. Watch results under **Recordings**. Revoke a computer any time from Security Center.

## Making a video (Stage 4)
1. **Script Studio:** create a script (optionally from a research report: you get empty scenes titled from page headings, never invented narration).
   For each scene write narration, pick a real recording as footage, and optionally set a start time or zoom.
2. **Narration:** upload your own audio per scene, or generate it with Piper (free, offline) or ElevenLabs once configured (Settings shows what is missing).
   Editing the narration marks its audio out of date, and it won't be used until you replace it.
3. **Subtitles:** edit the subtitle text per scene; download `.srt`. **YouTube details** holds title, description, tags and chapters taken from your real timeline.
4. **Video Studio:** choose 16:9, 9:16 or 1:1, optional intro/outro, burned-in subtitles and cursor highlight, then Render. Read the quality checks before approving.
5. **Thumbnail Studio:** make several versions from a real screenshot, mark one as selected and export the PNG.

## Publishing to YouTube (Stage 5)
1. Read `docs/YOUTUBE_SETUP.md` first: uploads stay private until Google audits your API project, and the default quota is about 6 uploads a day.
2. **Publishing -> Connect a channel**, then optionally set the automatic-publishing defaults.
3. A finished render appears in **Approvals** with its quality checks, metadata and a video preview. Choose channel, visibility, an optional schedule, and answer
   the kids and AI-content questions. Approve to upload, or reject with a note.
4. **Publishing** shows progress, lets you retry a failed upload (it resumes) or cancel, and links to the video on YouTube.

## Keeping it healthy (Stage 6)
- **Analytics:** production throughput (renders and uploads per day, success rates, most-flagged quality checks, progress toward 50 a day) and YouTube views/likes/comments (refresh on demand).
- **Settings -> System health:** database, Redis, storage, FFmpeg, Chromium, workers and queues. "Recover now" marks stuck work failed so you can retry it (this also runs every 5 minutes).
- **Settings -> Database backups:** nightly automatic backups, plus "Back up now".
- **Security Center:** configuration checks, paired computers, and a filterable audit trail.
