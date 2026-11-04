"""Honest integration status: reports what is configured, never pretends."""
from app.core.config import Settings


def integration_status(s: Settings) -> list[dict]:
    def entry(key, label, required, needed_for, alternative=None):
        missing = [name for name, val in required.items() if not val]
        return {
            "key": key,
            "label": label,
            "configured": not missing,
            "missing": missing,
            "needed_for": needed_for,
            "local_alternative": alternative,
        }

    return [
        entry("firebase", "Firebase Authentication",
              {"FIREBASE_PROJECT_ID": s.firebase_project_id, "OWNER_EMAIL": s.owner_email},
              "Owner login", None),
        entry("anthropic", "Claude API", {"ANTHROPIC_API_KEY": s.anthropic_api_key},
              "Research, scripts, SEO, fact checking",
              "Agents report 'AI provider not configured' instead of producing output."),
        entry("tts_piper", "Piper text-to-speech (free, offline)",
              {"PIPER_BINARY": s.piper_binary, "PIPER_MODEL": s.piper_model},
              "Narration without paid services", "Upload your own narration audio for each scene."),
        entry("tts_elevenlabs", "ElevenLabs text-to-speech (paid)",
              {"ELEVENLABS_API_KEY": s.elevenlabs_api_key, "ELEVENLABS_VOICE_ID": s.elevenlabs_voice_id},
              "Higher-quality narration", "Use Piper or upload your own narration audio."),
        entry("storage", "Object storage (S3-compatible)",
              {"S3_BUCKET": s.s3_bucket, "S3_ACCESS_KEY_ID": s.s3_access_key_id,
               "S3_SECRET_ACCESS_KEY": s.s3_secret_access_key},
              "Production recordings and renders", "Local disk storage is used in development."),
        entry("youtube", "YouTube Data API",
              {"YOUTUBE_CLIENT_ID": s.youtube_client_id, "YOUTUBE_CLIENT_SECRET": s.youtube_client_secret,
               "YOUTUBE_REDIRECT_URI": s.youtube_redirect_uri, "TOKEN_ENCRYPTION_KEY": s.token_encryption_key},
              "Channel connection and uploads", "Export the finished video and upload it manually."),
    ]
