# YouTube setup (do this only after everything else is tested)

## 1. Google Cloud project
1. console.cloud.google.com -> create a project -> **APIs & Services -> Library -> YouTube Data API v3 -> Enable**.
2. **OAuth consent screen**: user type *External*, add yourself as a test user. Add the scopes
   `.../auth/youtube.upload` and `.../auth/youtube.readonly` (the app asks for nothing broader, so it cannot delete videos
   or change channel settings).
3. **Credentials -> Create OAuth client ID -> Web application.** Authorised redirect URI must match `YOUTUBE_REDIRECT_URI` exactly,
   for example `https://YOUR-API/api/youtube/oauth/callback`.
4. Put the client ID/secret in `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`, and generate `TOKEN_ENCRYPTION_KEY`
   (command in `.env.example`). Open **Publishing -> Connect a channel**.

## 2. Things that will surprise you (verified against Google's documentation)
- **Private-only until audited.** Videos uploaded through `videos.insert` by an API project created after 28 July 2020 that has not
  passed Google's compliance audit are restricted to *private*, whatever visibility the app requests. Until you pass the audit,
  public and unlisted uploads are not possible. Request it via the YouTube API Services audit form
  (https://support.google.com/youtube/contact/yt_api_form), choosing *Quota Extension Request* if you also want more quota.
- **Quota.** The default is 10,000 units/day. Google's reference lists 1,600 units per upload, so about 6 uploads a day.
  Your goal of 50 a day needs roughly 82,500 units a day, which means a quota extension. Some sources describe a newer per-endpoint
  upload bucket; check the quota page in your Cloud Console and set `YOUTUBE_UPLOAD_COST` / `YOUTUBE_DAILY_QUOTA` to what it shows.
- **Channel limit.** Separately from API quota, YouTube limits how many videos a *channel* can upload in 24 hours, and manual uploads count.
  The app reports this as its own error.
- **Testing mode tokens.** While the consent screen is in *Testing*, Google expires refresh tokens after about 7 days, so you would have
  to reconnect weekly. Moving the consent screen to *In production* (unverified is fine for your own account) avoids that.
- **Disclosures.** You must answer "made for kids" and "contains realistic AI-generated content" for every video. The app requires explicit
  answers and forces the AI disclosure on when an AI voice was used.

## 3. Safe rollout
1. Connect your channel. Keep projects on **approval** mode and upload as **private**.
2. Upload one video, open it on YouTube, check title, description, chapters, thumbnail and disclosures.
3. Only then consider automatic mode: set Publishing defaults, and remember automatic mode refuses anything with text-card scenes,
   missing narration, metadata warnings or a repeated title.
