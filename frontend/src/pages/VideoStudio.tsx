import { useEffect, useState } from "react";
import { ProjectPicker, useProjectId, useProjects } from "../components/ProjectPicker";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { RenderInfo } from "../types/api";

const tone = (s: string) => (s === "ready" ? "ok" : s === "failed" ? "bad" : s === "rendering" || s === "queued" ? "warn" : "mute") as "ok" | "bad" | "warn" | "mute";
const qTone = (s: string) => (s === "pass" ? "ok" : s === "fail" ? "bad" : "warn") as "ok" | "bad" | "warn";

function RenderCard({ r, onCancel }: { r: RenderInfo; onCancel: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => () => { if (src) URL.revokeObjectURL(src); }, [src]);
  const active = r.status === "queued" || r.status === "rendering";
  async function load() { try { setSrc(await api.renderUrl(r.id)); } catch { setErr("Couldn't load the video."); } }
  return (
    <li className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{r.aspect_ratio} · {r.width}×{r.height} · {r.fps} fps{r.duration_seconds ? ` · ${r.duration_seconds.toFixed(1)}s` : ""}</p>
        <Pill tone={tone(r.status)}>{r.status}</Pill>
      </div>
      {active && (
        <>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={Math.round(r.progress * 100)} aria-valuemin={0} aria-valuemax={100}><div className="h-full bg-accent transition-all" style={{ width: `${Math.round(r.progress * 100)}%` }} /></div>
          <div className="mt-2"><Button variant="danger" onClick={onCancel}>Cancel</Button></div>
        </>
      )}
      {r.error && <p className="mt-2 text-sm text-warn">{r.error}</p>}
      {r.quality.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {r.quality.map((c) => <li key={c.name} className="flex items-start gap-2"><Pill tone={qTone(c.status)}>{c.status}</Pill><span className="text-mute">{c.detail}</span></li>)}
        </ul>
      )}
      {r.warnings.map((w, i) => <p key={i} className="mt-1 text-xs text-warn">{w}</p>)}
      {r.has_file && (
        <div className="mt-3">
          {!src ? <Button variant="ghost" onClick={() => void load()}>Preview</Button> : (
            <>
              <video src={src} controls className="w-full max-w-xl rounded-lg border border-line bg-black" />
              <a href={src} download="video.mp4" className="mt-2 inline-flex min-h-11 items-center rounded-lg border border-line px-4 text-sm hover:bg-raised">Download .mp4</a>
            </>
          )}
          {err && <Notice tone="error">{err}</Notice>}
        </div>
      )}
    </li>
  );
}

export default function VideoStudio() {
  const projects = useProjects();
  const [projectId, setProjectId] = useProjectId(projects.data);
  const scripts = useApi(() => (projectId ? api.scripts(projectId) : Promise.resolve([])), [projectId]);
  const renders = useApi(api.renders);
  const [scriptId, setScriptId] = useState("");
  const [form, setForm] = useState({ aspect_ratio: "16:9", fps: 30, burn_subtitles: false, cursor_highlight: true, intro_text: "", outro_text: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const chosen = scriptId || scripts.data?.[0]?.id || "";
  const ids = new Set((scripts.data ?? []).map((s) => s.id));
  const mine = (renders.data ?? []).filter((r) => r.script_id && ids.has(r.script_id));
  const active = mine.some((r) => r.status === "queued" || r.status === "rendering");
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => void renders.reload(), 2000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  async function start(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      await api.startRender(chosen, { ...form, intro_text: form.intro_text || undefined, outro_text: form.outro_text || undefined });
      await renders.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't start the render"); }
    finally { setBusy(false); }
  }

  if (projects.loading) return <Loading />;
  if (!projects.data?.length) return <Panel><Empty title="Create a project first" hint="Videos are rendered from a project's scripts." /></Panel>;

  return (
    <>
      <PageHeader title="Video Studio" subtitle="Render a script into a video using your real recordings and narration, then review the quality checks." />
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Panel className="h-fit p-4">
          <form className="space-y-3" onSubmit={start}>
            {error && <Notice tone="error">{error}</Notice>}
            <ProjectPicker projects={projects.data} value={projectId} onChange={(id) => { setProjectId(id); setScriptId(""); }} />
            <Field label="Script">
              <select className={inputClass} value={chosen} onChange={(e) => setScriptId(e.target.value)}>
                {scripts.data?.length === 0 && <option value="">No scripts</option>}
                {scripts.data?.map((s) => <option key={s.id} value={s.id}>{s.title} ({s.scene_count} scenes)</option>)}
              </select>
            </Field>
            <Field label="Shape">
              <select className={inputClass} value={form.aspect_ratio} onChange={(e) => setForm({ ...form, aspect_ratio: e.target.value })}>
                <option value="16:9">Landscape 16:9 (1920×1080)</option><option value="9:16">Vertical 9:16 (1080×1920)</option><option value="1:1">Square 1:1 (1080×1080)</option>
              </select>
            </Field>
            <Field label="Frames per second"><input className={inputClass} type="number" min={12} max={60} value={form.fps} onChange={(e) => setForm({ ...form, fps: Number(e.target.value) })} /></Field>
            <Field label="Intro title (optional)"><input className={inputClass} maxLength={120} value={form.intro_text} onChange={(e) => setForm({ ...form, intro_text: e.target.value })} /></Field>
            <Field label="Outro text (optional)"><input className={inputClass} maxLength={120} value={form.outro_text} onChange={(e) => setForm({ ...form, outro_text: e.target.value })} /></Field>
            <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={form.burn_subtitles} onChange={(e) => setForm({ ...form, burn_subtitles: e.target.checked })} />Burn subtitles into the video</label>
            <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={form.cursor_highlight} onChange={(e) => setForm({ ...form, cursor_highlight: e.target.checked })} />Highlight the cursor</label>
            <Button type="submit" className="w-full" loading={busy} disabled={!chosen}>Render video</Button>
            <p className="text-xs text-mute">Scenes without a recording become plain text cards, and the quality check says so.</p>
          </form>
        </Panel>
        <Panel>
          {renders.loading ? <Loading /> : renders.error ? <div className="p-4"><Notice tone="error">{renders.error}</Notice></div> :
            mine.length ? <ul className="divide-y divide-line">{mine.map((r) => <RenderCard key={r.id} r={r} onCancel={() => void api.cancelRender(r.id).then(() => renders.reload())} />)}</ul>
              : <Empty title="No renders yet" hint="Pick a script and press Render video." />}
        </Panel>
      </div>
    </>
  );
}
