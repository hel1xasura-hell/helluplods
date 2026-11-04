import { useState } from "react";
import { BarChart } from "../components/BarChart";
import { Button, Empty, Loading, Notice, PageHeader, Panel } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return <Panel className="p-4"><p className="text-sm text-mute">{label}</p><p className="mt-1 font-display text-2xl font-bold tabular-nums">{value}</p>{hint && <p className="mt-1 text-xs text-mute">{hint}</p>}</Panel>;
}

export default function Analytics() {
  const [days, setDays] = useState(14);
  const prod = useApi(() => api.production(days), [days]);
  const yt = useApi(api.ytStats);
  const [msg, setMsg] = useState<{ tone: "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function sync() {
    setBusy(true); setMsg(null);
    try { const r = await api.syncYt(); setMsg({ tone: "info", text: `Updated ${r.synced} video${r.synced === 1 ? "" : "s"}.` }); await yt.reload(); }
    catch (e) { setMsg({ tone: "error", text: e instanceof Error ? e.message : "Couldn't sync" }); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Analytics" subtitle="Production throughput from your own records, plus view counts pulled from YouTube."
        action={<select aria-label="Time range" className="min-h-11 rounded-lg border border-line bg-bg px-3 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option></select>} />
      {prod.loading ? <Loading /> : prod.error || !prod.data ? <Notice tone="error">{prod.error ?? "No data"}</Notice> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Videos rendered" value={prod.data.totals.renders_ready} hint={`${prod.data.totals.renders} started`} />
            <Stat label="Uploaded" value={prod.data.totals.uploads} />
            <Stat label="Render success" value={pct(prod.data.render_success_rate)} hint={prod.data.avg_render_seconds ? `avg ${prod.data.avg_render_seconds.toFixed(0)} s` : undefined} />
            <Stat label="Upload success" value={pct(prod.data.upload_success_rate)} />
          </div>
          <Panel className="mt-4 p-4">
            <p className="text-sm text-mute">Progress toward {prod.data.target_per_day} uploads a day</p>
            <p className="mt-1 font-display text-2xl font-bold">{pct(prod.data.progress_toward_target)}</p>
            <p className="mt-1 text-xs text-mute">Measured over the last {prod.data.days} days. YouTube's quota and your channel's upload limit set the real ceiling; see Publishing.</p>
          </Panel>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Panel className="p-4"><h2 className="mb-2 text-base font-semibold">Renders per day</h2><BarChart data={prod.data.renders_per_day} label="Renders per day" /></Panel>
            <Panel className="p-4"><h2 className="mb-2 text-base font-semibold">Uploads per day</h2><BarChart data={prod.data.uploads_per_day} label="Uploads per day" /></Panel>
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Panel className="p-4">
              <h2 className="text-base font-semibold">Approvals</h2>
              <ul className="mt-2 space-y-1 text-sm">{Object.entries(prod.data.approval_funnel).map(([k, v]) => <li key={k} className="flex justify-between"><span className="text-mute">{k.replace("_", " ")}</span><span className="tabular-nums">{v}</span></li>)}</ul>
            </Panel>
            <Panel className="p-4">
              <h2 className="text-base font-semibold">Most flagged quality checks</h2>
              {prod.data.most_flagged_quality_checks.length === 0 ? <p className="mt-2 text-sm text-mute">Nothing flagged.</p> :
                <ul className="mt-2 space-y-1 text-sm">{prod.data.most_flagged_quality_checks.map(([k, v]) => <li key={k} className="flex justify-between"><span className="text-mute">{k.replace("_", " ")}</span><span className="tabular-nums">{v}</span></li>)}</ul>}
            </Panel>
          </div>
        </>
      )}
      <Panel className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-lg font-semibold">YouTube performance</h2>
          <Button variant="ghost" loading={busy} onClick={() => void sync()}>Refresh from YouTube</Button>
        </div>
        {msg && <div className="p-4"><Notice tone={msg.tone}>{msg.text}</Notice></div>}
        {yt.loading ? <Loading /> : yt.data && yt.data.videos.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-mute"><tr><th className="px-4 py-2">Video</th><th className="px-2">Views</th><th className="px-2">Likes</th><th className="px-2">Comments</th></tr></thead>
              <tbody className="divide-y divide-line">
                {yt.data.videos.map((v) => <tr key={v.video_id}><td className="max-w-[16rem] truncate px-4 py-2">{v.title}</td><td className="px-2 tabular-nums">{v.views ?? "–"}</td><td className="px-2 tabular-nums">{v.likes ?? "–"}</td><td className="px-2 tabular-nums">{v.comments ?? "–"}</td></tr>)}
                <tr className="font-medium"><td className="px-4 py-2">Total</td><td className="px-2 tabular-nums">{yt.data.totals.views}</td><td className="px-2 tabular-nums">{yt.data.totals.likes}</td><td className="px-2 tabular-nums">{yt.data.totals.comments}</td></tr>
              </tbody>
            </table>
          </div>
        ) : <Empty title="No uploaded videos yet" hint="Statistics appear after your first upload. Refreshing costs 1 YouTube quota unit per 50 videos." />}
      </Panel>
    </>
  );
}
