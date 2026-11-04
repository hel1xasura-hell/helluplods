"""The 16 specialised agents. Stage 1 defines contracts, permissions and limits; implementations
arrive in the stage listed. Unbuilt agents raise NotImplementedYet and report that honestly."""
from pydantic import BaseModel, Field

from app.agents.base import AgentSpec, NotImplementedYet


class TargetInput(BaseModel):
    project_id: str
    target: str = Field(min_length=1, max_length=2048)


class ProjectInput(BaseModel):
    project_id: str


class GenericOutput(BaseModel):
    summary: str
    data: dict = Field(default_factory=dict)


def _spec(key, name, resp, stage, tools=(), secrets=(), timeout=300.0, retries=2, inp=ProjectInput):
    return AgentSpec(key, name, resp, stage, inp, GenericOutput, frozenset(tools), frozenset(secrets),
                     timeout, retries)


AI = ("ANTHROPIC_API_KEY",)
AGENTS: dict[str, AgentSpec] = {s.key: s for s in [
    _spec("research", "Research Agent", "Resolve targets, collect official info, draft the research report.", 2,
          ("web_fetch", "ai_complete"), AI, 600, 2, TargetInput),
    _spec("website_verification", "Website Verification Agent", "Verify identity, redirects and canonical URL.", 2,
          ("web_fetch",), (), 120, 2, TargetInput),
    _spec("feature_exploration", "Feature Exploration Agent", "Explore menus, navigation and workflows.", 2,
          ("browser", "ai_complete"), AI, 900, 1),
    _spec("fact_checking", "Fact Checking Agent", "Check claims against recorded sources.", 2,
          ("web_fetch", "ai_complete"), AI, 300, 2),
    _spec("script_writing", "Script Writing Agent", "Write tutorial scripts from verified research.", 4,
          ("ai_complete",), AI, 300, 2),
    _spec("scene_planning", "Scene Planning Agent", "Plan scenes and assign footage.", 4, ("ai_complete",), AI, 300, 2),
    _spec("browser", "Browser Agent", "Drive Playwright sessions inside SSRF-safe contexts.", 2, ("browser",), (), 900, 1),
    _spec("screenshot", "Screenshot Agent", "Capture and store real screenshots.", 2, ("browser", "storage"), (), 120, 2),
    _spec("screen_recording", "Screen Recording Agent", "Record real browser or device sessions.", 3,
          ("browser", "storage"), (), 1800, 1),
    _spec("voice_generation", "Voice Generation Agent", "Generate narration audio.", 4, ("tts", "storage"), (), 600, 2),
    _spec("video_editing", "Video Editing Agent", "Assemble and render with FFmpeg.", 4, ("ffmpeg", "storage"), (), 3600, 1),
    _spec("subtitle", "Subtitle Agent", "Create and align subtitles.", 4, ("storage",), (), 300, 2),
    _spec("thumbnail", "Thumbnail Agent", "Create thumbnail concepts and renders.", 4, ("ai_complete", "storage"), AI, 300, 2),
    _spec("seo_metadata", "SEO Metadata Agent", "Titles, descriptions, chapters, tags.", 4, ("ai_complete",), AI, 300, 2),
    _spec("quality_control", "Quality Control Agent", "Check renders and metadata before approval.", 4,
          ("ffmpeg", "ai_complete"), AI, 600, 1),
    _spec("youtube_publishing", "YouTube Publishing Agent", "Upload approved videos via the official API.", 5,
          ("youtube",), ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY"), 3600, 3),
]}


async def not_built(_input, ctx):
    raise NotImplementedYet(f"{ctx.spec.name} ships in stage {ctx.spec.stage}.")


IMPLEMENTATIONS = {key: not_built for key in AGENTS}
