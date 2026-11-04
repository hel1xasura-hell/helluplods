import type {
  AgentInfo, ApprovalInfo, AuditItem, BackupList, HealthInfo, ProductionStats, SecurityCheck, YtStats, Dashboard, DeviceInfo, PublishDefaults, UploadInfo, YtStatus, Integration, MetadataView, RenderInfo, SceneInfo, ScriptFull, ScriptSummary, ShotInfo,
  ThumbInfo, VoiceStatus, RecordingInfo, RecordingTask, NotificationList, Owner, RunInfo, Project, Report, ResearchTarget, TargetKind } from "../types/api";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export type TokenProvider = () => Promise<string | null>;
let tokenProvider: TokenProvider = async () => null;
export const getToken = () => tokenProvider();
export const wsBase = () => BASE.replace(/^http/, "ws");
export const setTokenProvider = (p: TokenProvider) => { tokenProvider = p; };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenProvider();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check that the backend is running.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

async function blobUrl(path: string): Promise<string> {
  const token = await tokenProvider();
  const res = await fetch(`${BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, "Couldn't load the image");
  return URL.createObjectURL(await res.blob());
}

async function putRaw<T>(path: string, body: Blob): Promise<T> {
  const token = await tokenProvider();
  const res = await fetch(`${BASE}${path}`, { method: "PUT", body, headers: { "Content-Type": "application/octet-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try { const b = await res.json(); detail = typeof b.detail === "string" ? b.detail : detail; } catch { /* keep */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown) => ({ body: JSON.stringify(body) });

export const api = {
  me: () => request<Owner>("/api/me"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  agents: () => request<AgentInfo[]>("/api/agents"),
  integrations: () => request<Integration[]>("/api/integrations"),
  projects: () => request<Project[]>("/api/projects"),
  createProject: (body: { name: string; description?: string; execution_mode: string; publishing_mode: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  devices: () => request<DeviceInfo[]>("/api/devices"),
  createPairingCode: () => request<{ code: string; expires_at: string }>("/api/devices/pairing-codes", { method: "POST" }),
  revokeDevice: (id: string) => request<void>(`/api/devices/${id}`, { method: "DELETE" }),
  recordTarget: (targetId: string, duration_seconds = 10) =>
    request<{ task_id: string; executor: string; status: string }>(`/api/targets/${targetId}/record`, { method: "POST", body: JSON.stringify({ duration_seconds }) }),
  recordings: () => request<RecordingInfo[]>("/api/recordings"),
  recordingTasks: () => request<RecordingTask[]>("/api/recording-tasks"),
  recordingUrl: (id: string) => blobUrl(`/api/recordings/${id}/file`),
  pauseRun: (id: string) => request<RunInfo>(`/api/runs/${id}/pause`, { method: "POST" }),
  resumeRun: (id: string) => request<RunInfo>(`/api/runs/${id}/resume`, { method: "POST" }),
  stopRun: (id: string) => request<RunInfo>(`/api/runs/${id}/stop`, { method: "POST" }),
  runs: () => request<RunInfo[]>("/api/runs"),
  notifications: () => request<NotificationList>("/api/notifications"),
  markRead: (id: string) => request<void>(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => request<void>("/api/notifications/read-all", { method: "POST" }),
  startResearch: (targetId: string) => request<{ status: string }>(`/api/targets/${targetId}/research`, { method: "POST" }),
  report: (targetId: string) => request<Report>(`/api/targets/${targetId}/report`),
  screenshot: (id: string) => blobUrl(`/api/screenshots/${id}`),
  targets: (projectId: string) => request<ResearchTarget[]>(`/api/projects/${projectId}/targets`),
  addTarget: (projectId: string, body: { kind: TargetKind; value: string }) =>
    request<ResearchTarget>(`/api/projects/${projectId}/targets`, { method: "POST", body: JSON.stringify(body) }),
  scripts: (projectId: string) => request<ScriptSummary[]>(`/api/projects/${projectId}/scripts`),
  createScript: (projectId: string, body: { title: string; from_target_id?: string }) =>
    request<ScriptFull>(`/api/projects/${projectId}/scripts`, { method: "POST", ...json(body) }),
  script: (id: string) => request<ScriptFull>(`/api/scripts/${id}`),
  deleteScript: (id: string) => request<void>(`/api/scripts/${id}`, { method: "DELETE" }),
  addScene: (scriptId: string, body: { narration: string; title?: string }) =>
    request<SceneInfo>(`/api/scripts/${scriptId}/scenes`, { method: "POST", ...json(body) }),
  patchScene: (id: string, body: Partial<Pick<SceneInfo, "title" | "narration" | "subtitle" | "recording_id" | "options">>) =>
    request<SceneInfo>(`/api/scenes/${id}`, { method: "PATCH", ...json(body) }),
  deleteScene: (id: string) => request<void>(`/api/scenes/${id}`, { method: "DELETE" }),
  reorderScenes: (scriptId: string, order: string[]) =>
    request<ScriptFull>(`/api/scripts/${scriptId}/scenes/reorder`, { method: "POST", ...json({ order }) }),
  uploadAudio: (sceneId: string, file: Blob) => putRaw<SceneInfo>(`/api/scenes/${sceneId}/audio`, file),
  audioUrl: (sceneId: string) => blobUrl(`/api/scenes/${sceneId}/audio`),
  voices: () => request<VoiceStatus[]>("/api/voices"),
  generateVoice: (scriptId: string, provider: string) =>
    request<{ status: string }>(`/api/scripts/${scriptId}/voice`, { method: "POST", ...json({ provider }) }),
  generateAi: (scriptId: string, targetId: string) =>
    request<ScriptFull>(`/api/scripts/${scriptId}/generate-ai?target_id=${targetId}`, { method: "POST" }),
  metadata: (scriptId: string) => request<MetadataView>(`/api/scripts/${scriptId}/metadata`),
  saveMetadata: (scriptId: string, body: { title: string; description: string; tags: string[] }) =>
    request<unknown>(`/api/scripts/${scriptId}/metadata`, { method: "PUT", ...json(body) }),
  subtitlesText: async (scriptId: string, fmt: "srt" | "vtt") => {
    const t = await tokenProvider();
    const r = await fetch(`${BASE}/api/scripts/${scriptId}/subtitles.${fmt}`, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
    if (!r.ok) throw new ApiError(r.status, "Couldn't load subtitles");
    return r.text();
  },
  startRender: (scriptId: string, body: Record<string, unknown>) =>
    request<RenderInfo>(`/api/scripts/${scriptId}/render`, { method: "POST", ...json(body) }),
  renders: () => request<RenderInfo[]>("/api/renders"),
  cancelRender: (id: string) => request<RenderInfo>(`/api/renders/${id}/cancel`, { method: "POST" }),
  renderUrl: (id: string) => blobUrl(`/api/renders/${id}/file`),
  screenshots: (projectId: string) => request<ShotInfo[]>(`/api/projects/${projectId}/screenshots`),
  screenshotUrl: (id: string) => blobUrl(`/api/screenshots/${id}`),
  thumbnails: (projectId: string) => request<ThumbInfo[]>(`/api/projects/${projectId}/thumbnails`),
  templates: () => request<string[]>("/api/thumbnail-templates"),
  createThumbnail: (projectId: string, body: { text: string; template: string; accent: string; screenshot_id?: string; brand?: string }) =>
    request<ThumbInfo>(`/api/projects/${projectId}/thumbnails`, { method: "POST", ...json(body) }),
  selectThumbnail: (id: string) => request<ThumbInfo>(`/api/thumbnails/${id}/select`, { method: "POST" }),
  deleteThumbnail: (id: string) => request<void>(`/api/thumbnails/${id}`, { method: "DELETE" }),
  thumbnailUrl: (id: string) => blobUrl(`/api/thumbnails/${id}/file`),
  youtubeStatus: () => request<YtStatus>("/api/youtube/status"),
  oauthStart: () => request<{ auth_url: string }>("/api/youtube/oauth/start", { method: "POST" }),
  disconnectYoutube: (id: string) => request<void>(`/api/youtube/accounts/${id}`, { method: "DELETE" }),
  defaults: () => request<Partial<PublishDefaults>>("/api/publishing/defaults"),
  saveDefaults: (body: PublishDefaults) => request<PublishDefaults>("/api/publishing/defaults", { method: "PUT", ...json(body) }),
  approvals: () => request<ApprovalInfo[]>("/api/approvals"),
  approve: (id: string, body: Record<string, unknown>) => request<{ upload_job_id: string; status: string }>(`/api/approvals/${id}/approve`, { method: "POST", ...json(body) }),
  reject: (id: string, note: string) => request<ApprovalInfo>(`/api/approvals/${id}/reject`, { method: "POST", ...json({ note: note || null }) }),
  uploads: () => request<UploadInfo[]>("/api/uploads"),
  retryUpload: (id: string) => request<UploadInfo>(`/api/uploads/${id}/retry`, { method: "POST" }),
  cancelUpload: (id: string) => request<UploadInfo>(`/api/uploads/${id}/cancel`, { method: "POST" }),
  production: (days = 14) => request<ProductionStats>(`/api/analytics/production?days=${days}`),
  ytStats: () => request<YtStats>("/api/analytics/youtube"),
  syncYt: () => request<{ synced: number }>("/api/analytics/youtube/sync", { method: "POST" }),
  health: () => request<HealthInfo>("/api/system/health"),
  recoverStuck: () => request<Record<string, number>>("/api/system/recover", { method: "POST" }),
  securityChecks: () => request<SecurityCheck[]>("/api/security/checks"),
  audit: (action = "", before = "") => request<AuditItem[]>(`/api/audit?limit=50${action ? `&action=${encodeURIComponent(action)}` : ""}${before ? `&before=${encodeURIComponent(before)}` : ""}`),
  backups: () => request<BackupList>("/api/backups"),
  createBackup: () => request<{ status: string }>("/api/backups", { method: "POST" }),
};
