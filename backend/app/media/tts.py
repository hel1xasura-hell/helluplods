"""Text-to-speech providers + audio file validation. Providers report honestly when they are not configured."""
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from app.core.config import Settings


class TTSNotConfigured(RuntimeError):
    pass


class TTSProvider(Protocol):
    name: str
    extension: str

    def missing(self) -> list[str]: ...
    async def synthesize(self, text: str, out_path: Path) -> Path: ...


class PiperProvider:
    name, extension = "piper", ".wav"

    def __init__(self, binary: str, model: str):
        self.binary, self.model = binary, model

    def missing(self) -> list[str]:
        out = []
        if not self.binary or not (Path(self.binary).exists() or shutil.which(self.binary)):
            out.append("PIPER_BINARY")
        if not self.model or not Path(self.model).exists():
            out.append("PIPER_MODEL")
        return out

    async def synthesize(self, text: str, out_path: Path) -> Path:
        if self.missing():
            raise TTSNotConfigured(f"Piper is not configured: {', '.join(self.missing())}")

        def run():
            proc = subprocess.run([self.binary, "--model", self.model, "--output_file", str(out_path)],
                                  input=text, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0 or not out_path.exists():
                raise RuntimeError(f"Piper failed: {proc.stderr.strip()[-300:]}")

        await asyncio.to_thread(run)
        return out_path


class ElevenLabsProvider:
    name, extension = "elevenlabs", ".mp3"

    def __init__(self, api_key: str, voice_id: str, transport: "httpx.AsyncBaseTransport | None" = None):
        self.api_key, self.voice_id, self.transport = api_key, voice_id, transport

    def missing(self) -> list[str]:
        return [n for n, v in (("ELEVENLABS_API_KEY", self.api_key), ("ELEVENLABS_VOICE_ID", self.voice_id)) if not v]

    async def synthesize(self, text: str, out_path: Path) -> Path:
        if self.missing():
            raise TTSNotConfigured(f"ElevenLabs is not configured: {', '.join(self.missing())}")
        import httpx

        async with httpx.AsyncClient(timeout=120, transport=self.transport) as client:
            resp = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                                     headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                                     json={"text": text, "model_id": "eleven_multilingual_v2"})
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


def providers(settings: "Settings") -> dict[str, TTSProvider]:
    return {"piper": PiperProvider(settings.piper_binary, settings.piper_model),
            "elevenlabs": ElevenLabsProvider(settings.elevenlabs_api_key, settings.elevenlabs_voice_id)}


def provider_status(settings: "Settings") -> list[dict]:
    return [{"name": n, "configured": not p.missing(), "missing": p.missing()} for n, p in providers(settings).items()]


def looks_like_audio(head: bytes) -> str | None:
    """Return the extension for WAV / MP3 / OGG / M4A / WebM by magic bytes, else None."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return ".mp3"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[4:8] == b"ftyp":
        return ".m4a"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    return None
