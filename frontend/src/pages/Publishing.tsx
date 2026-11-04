import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

const ERRORS: Record<string, string> = {
  cancelled: "Connection cancelled.", invalid_state: "That sign-in link was invalid or expired. Try again.",
  no_refresh_token: "Google didn't grant offline access. Remove this app at myaccount.google.com/permissions and connect again.",
  not_configured: "YouTube isn't configured on the server yet.",
};
const tone = (s: string) => (s === "published" || s === "uploaded" || s === "scheduled" ? "ok" : s === "failed" ? "bad" : s === "cancelled" ? "mute" : "warn") as "ok" | "bad" | "warn" | "mute";

export default function Publishing() {
  const [params, setParams] = useSearchParams();
  const yt = useApi(api.youtubeStatus);
  const uploads = useApi(api.uploads);
  const defaults = useApi(api.defaults);
  const [error, setError] = useState<string | null>(params.get("error") ? (ERRORS[params.get("error")!] ?? "Couldn't connect YouTube.") : null);
  const [notice, setNotice] = useState<string | null>(params.get("connected") ? "YouTube channel connected." : null);
  const [form, setForm] = useState({ visibility: "private", made_for_kids: "no", contains_synthetic_media: "yes", daily_limit: 3, hours: "" });

  useEffect(() => { if (params.get("connected") || params.get("error")) setParams({}, { replace: true }); }, [params, setParams]);
  useEffect(() => {
    const d = defaults.data;
    if (d && d.visibility) setForm({ visibility: d.visibility, made_for_kids: d.made_for_kids ? "yes" : "no", contains_synthetic_media: d.contains_synthetic_media ? "yes" : "no", daily_limit: d.daily_limit ?? 3, hours: (d.publish_hours_utc ?? []).join(", ") });
  }, [defaults.data]);

  const active = uploads.data?.some((u) => u.status === "queued" || u.status === "uploading") ?? false;
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => void uploads.reload(), 2500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const guard = async (fn: () => Promise<void>) => { setError(null); setNotice(null); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong"); } };
  if (yt.loading) return <Loading />;
  const s = yt.data;

  return (
    <>
      <PageHeader title="Publishing" subtitle="Connect your channel, set safe defaults for automatic mode, and follow every upload." />
      {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      {notice && <div className="mb-4"><Notice tone="info">{notice}</Notice></div>}

      <Panel className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">YouTube</h2>
          <Button disabled={!s?.configured} onClick={() => void guard(async () => { const r = await api.oauthStart(); window.location.href = r.auth_url; })}>Connect a channel</Button>
        </div>
        {s && !s.configured && <div className="mt-3"><Notice tone="warn">Not configured. Missing: {s.missing.join(", ")}. See FIREBASE_AUTH_SETUP.md and ENVIRONMENT_VARIABLES.md.</Notice></div>}
        {s?.accounts.filter((a) => a.status !== "disconnected").map((a) => (
          <div key={a.id} className="mt-4 rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{a.channel_title}</p>
              <div className="flex items-center gap-2"><Pill tone={a.status === "connected" ? "ok" : "warn"}>{a.status === "reauthorize" ? "reconnect needed" : a.status}</Pill>
                <Button variant="danger" onClick={() => void guard(async () => { if (window.confirm("Disconnect this channel? Your videos on YouTube are not touched.")) { await api.disconnectYoutube(a.id); await yt.reload(); } })}>Disconnect</Button></div>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={Math.round((a.quota_used_today / a.quota_limit) * 100)} aria-valuemin={0} aria-valuemax={100}><div className="h-full bg-accent" style={{ width: `${Math.min(100, (a.quota_used_today / a.quota_limit) * 100)}%` }} /></div>
            <p className="mt-1 text-xs text-mute">Quota today: {a.quota_used_today.toLocaleString()} of {a.quota_limit.toLocaleString()} units · about {a.uploads_left_today} uploads left</p>
          </div>
        ))}
        {s && <p className="mt-3 text-xs text-mute">{s.quota_note} At your current quota that is about {s.uploads_per_day_at_this_quota} uploads a day.</p>}
        {s && <div className="mt-3"><Notice tone="warn">{s.audit_note}</Notice></div>}
        {s && <p className="mt-1 text-xs text-mute">This app can upload videos and read your channel name. It cannot delete videos or change channel settings.</p>}
      </Panel>

      <Panel className="mt-6 p-4">
        <h2 className="text-lg font-semibold">Automatic publishing defaults</h2>
        <p className="mt-1 text-sm text-mute">Used only by projects set to "Upload automatically". Anything that fails a policy check goes to Approvals instead.</p>
        <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void guard(async () => {
          await api.saveDefaults({ visibility: form.visibility, made_for_kids: form.made_for_kids === "yes", contains_synthetic_media: form.contains_synthetic_media === "yes", daily_limit: Number(form.daily_limit), publish_hours_utc: form.hours.split(",").map((h) => h.trim()).filter(Boolean).map(Number) });
          setNotice("Defaults saved."); await defaults.reload(); }); }}>
          <Field label="Visibility"><select className={inputClass} value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></Field>
          <Field label="Uploads per day (max)"><input className={inputClass} type="number" min={1} max={50} value={form.daily_limit} onChange={(e) => setForm({ ...form, daily_limit: Number(e.target.value) })} /></Field>
          <Field label="Made for kids?"><select className={inputClass} value={form.made_for_kids} onChange={(e) => setForm({ ...form, made_for_kids: e.target.value })}><option value="no">No</option><option value="yes">Yes</option></select></Field>
          <Field label="Disclose AI-generated content?"><select className={inputClass} value={form.contains_synthetic_media} onChange={(e) => setForm({ ...form, contains_synthetic_media: e.target.value })}><option value="yes">Yes</option><option value="no">No</option></select></Field>
          <Field label="Publish hours, UTC (e.g. 14, 18). Empty = upload right away"><input className={inputClass} value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} /></Field>
          <div className="self-end"><Button type="submit">Save defaults</Button></div>
        </form>
      </Panel>

      <Panel className="mt-6">
        <h2 className="border-b border-line px-4 py-3 text-lg font-semibold">Uploads and schedule</h2>
        {uploads.loading ? <Loading /> : uploads.data?.length ? (
          <ul className="divide-y divide-line">
            {uploads.data.map((u) => (
              <li key={u.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="min-w-0 truncate font-medium">{u.title}</p><Pill tone={tone(u.status)}>{u.status}</Pill>
                </div>
                <p className="text-xs text-mute">{u.channel} · {u.visibility}{u.publish_at ? ` · goes live ${new Date(u.publish_at).toLocaleString()}` : ""}</p>
                {u.status === "uploading" && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={Math.round(u.progress * 100)} aria-valuemin={0} aria-valuemax={100}><div className="h-full bg-accent transition-all" style={{ width: `${Math.round(u.progress * 100)}%` }} /></div>}
                {u.error && <p className="mt-1 text-sm text-warn">{u.error}</p>}
                {u.warnings.map((w, i) => <p key={i} className="mt-1 text-xs text-warn">{w}</p>)}
                <div className="mt-2 flex flex-wrap gap-2">
                  {u.youtube_url && <a href={u.youtube_url} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center rounded-lg border border-line px-4 text-sm hover:bg-raised">Open on YouTube</a>}
                  {u.status === "failed" && <Button variant="ghost" onClick={() => void guard(async () => { await api.retryUpload(u.id); await uploads.reload(); })}>Retry (resumes)</Button>}
                  {(u.status === "queued" || u.status === "uploading") && <Button variant="danger" onClick={() => void guard(async () => { await api.cancelUpload(u.id); await uploads.reload(); })}>Cancel</Button>}
                </div>
              </li>
            ))}
          </ul>
        ) : <Empty title="No uploads yet" hint="Approve a finished video to upload it." />}
      </Panel>
    </>
  );
}
