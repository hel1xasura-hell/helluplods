export interface Owner { id: string; email: string; display_name: string | null }

export interface Project {
  id: string; name: string; description: string | null; status: string;
  execution_mode: "cloud" | "local" | "both"; publishing_mode: "approval" | "automatic"; created_at: string;
}

export type TargetKind = "website_url" | "website_name" | "android_app" | "play_url";

export interface ResearchTarget {
  id: string; project_id: string; kind: TargetKind; value: string;
  canonical_url: string | null; status: string; error: string | null; created_at: string;
}

export interface AgentInfo {
  key: string; name: string; responsibilities: string; stage: number; implemented: boolean;
  allowed_tools: string[]; timeout_seconds: number; max_retries: number;
}

export interface Integration {
  key: string; label: string; configured: boolean; missing: string[];
  needed_for: string; local_alternative: string | null;
}

export interface Dashboard {
  total_projects: number; research_tasks: number; active_agents: number; videos_rendering: number;
  videos_awaiting_approval: number; published_videos: number; failed_jobs: number;
  processing_queue: number; storage_bytes: number; cloud_workers: "not_connected" | "online";
  local_workers: number; recent_activity: { action: string; at: string; detail: Record<string, unknown> }[];
}

export interface ReportBody {
  target_name: string; canonical_url: string; description: string | null;
  features: { name: string; verified: boolean; evidence: string }[];
  limitations: string[]; screenshot_ids: string[];
  sources: { url: string; official: boolean; fetched_at: string | null }[];
  pricing: { pages_found: { label: string; href: string }[]; read: boolean; observed_prices: string[]; verified: boolean };
  pages_explored: { url: string; title: string; status: number | null }[];
  tutorial_opportunities: string[];
  tutorial_opportunities_source: string | null;
  verification: { verified_at: string; redirected: boolean; http_status: number | null; robots_checked: boolean };
  security_flags: { possible_prompt_injection: boolean };
  claim_checks: { claim: string; status: string; pages: string[]; method: string }[];
  tested_hands_on: boolean;
}

export interface Report { id: string; target_id: string; tested_hands_on: boolean; verified_at: string | null; body: ReportBody }

export interface NotificationItem { id: string; kind: string; title: string; body: string | null; read: boolean; created_at: string }
export interface NotificationList { unread: number; items: NotificationItem[] }
export interface RunInfo {
  id: string; agent_key: string; status: string; progress: number; current_url: string | null; control: string | null; error: string | null;
  started_at: string | null; finished_at: string | null;
  target: { id: string; value: string; canonical_url: string | null } | null;
}

export interface DeviceInfo { id: string; name: string; platform: string; revoked: boolean; online: boolean; last_seen_at: string | null }
export interface RecordingInfo {
  id: string; project_id: string; source_url: string | null; duration_seconds: number | null;
  executor: "cloud" | "local" | null; is_real_capture: boolean; width: number | null; height: number | null; created_at: string;
}
export interface RecordingTask { id: string; executor: string; status: string; url: string | null; error: string | null; created_at: string }

export interface SceneAudio { source: "tts" | "upload"; provider: string | null; duration_seconds: number | null; up_to_date: boolean }
export interface SceneInfo {
  id: string; position: number; title: string | null; narration: string; subtitle: string | null;
  recording_id: string | null; options: { trim_start?: number; min_seconds?: number; zoom?: { factor: number; cx: number; cy: number } };
  audio: SceneAudio | null;
}
export interface ScriptSummary { id: string; title: string; language: string; status: string; scene_count: number }
export interface ScriptFull { id: string; project_id: string; title: string; language: string; status: string; metadata: Record<string, unknown>; scenes: SceneInfo[] }
export interface MetadataView {
  metadata: { title?: string; description?: string; tags?: string[] }; chapters: { start: number; title: string }[];
  chapters_text: string; chapter_warnings: string[]; accuracy_warnings: string[];
}
export interface VoiceStatus { name: string; configured: boolean; missing: string[] }
export interface QualityCheck { name: string; status: "pass" | "warn" | "fail"; detail: string }
export interface RenderInfo {
  id: string; script_id: string | null; status: string; progress: number; aspect_ratio: string; width: number; height: number; fps: number;
  duration_seconds: number | null; quality: QualityCheck[]; warnings: string[]; error: string | null; has_file: boolean; created_at: string;
}
export interface ThumbInfo { id: string; text: string; template: string; accent: string; selected: boolean; created_at: string }
export interface ShotInfo { id: string; url: string | null; captured_at: string | null }

export interface YtAccount { id: string; channel_id: string; channel_title: string | null; status: string; quota_limit: number; quota_used_today: number; uploads_left_today: number }
export interface YtStatus { configured: boolean; missing: string[]; accounts: YtAccount[]; daily_quota: number; uploads_per_day_at_this_quota: number; quota_note: string; audit_note: string; upload_cost_units: number; scopes: string[] }
export interface ApprovalInfo {
  id: string; status: string; note: string | null; created_at: string; script_title: string | null;
  render: { id: string; duration_seconds: number | null; quality: QualityCheck[]; warnings: string[]; aspect_ratio: string } | null;
  metadata: { title?: string; description?: string; tags?: string[] }; accuracy_warnings: string[]; uses_ai_voice: boolean; thumbnail_id: string | null;
}
export interface UploadInfo {
  id: string; title: string | null; status: string; progress: number; visibility: string; publish_at: string | null; upload_at: string | null;
  error: string | null; attempts: number; youtube_video_id: string | null; youtube_url: string | null; channel: string | null; warnings: string[]; created_at: string;
}
export interface PublishDefaults { visibility: string; made_for_kids: boolean; contains_synthetic_media: boolean; daily_limit: number; publish_hours_utc: number[] }

export interface SeriesPoint { date: string; count: number }
export interface ProductionStats {
  days: number; renders_per_day: SeriesPoint[]; uploads_per_day: SeriesPoint[];
  totals: { renders: number; renders_ready: number; uploads: number; recordings: number; research_runs: number };
  render_success_rate: number | null; upload_success_rate: number | null; avg_render_seconds: number | null;
  approval_funnel: Record<string, number>; most_flagged_quality_checks: [string, number][]; target_per_day: number; progress_toward_target: number | null;
}
export interface YtStats { videos: { video_id: string; title: string | null; status: string; views: number | null; likes: number | null; comments: number | null; fetched_at: string | null }[]; totals: { views: number; likes: number; comments: number } }
export interface HealthInfo {
  components: { name: string; status: "ok" | "down"; detail: string }[]; workers_online: string[]; queue_depth: Record<string, number>;
  stuck: Record<string, number>; storage_bytes: number; overall: "ok" | "degraded";
}
export interface SecurityCheck { name: string; status: "pass" | "warn" | "fail"; detail: string }
export interface AuditItem { id: string; action: string; at: string; ip: string | null; detail: Record<string, unknown> }
export interface BackupList { pg_dump_available: boolean; database_is_postgres: boolean; items: { id: string; size_bytes: number; created_at: string; sha256: string | null }[] }
