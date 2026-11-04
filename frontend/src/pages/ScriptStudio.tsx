import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ProjectPicker, useProjectId, useProjects } from "../components/ProjectPicker";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { MetadataView, RecordingInfo, SceneInfo, ScriptFull } from "../types/api";

function SceneCard({ scene, index, total, recordings, onChange, onMove, onDelete, onError }: {
  scene: SceneInfo; index: number; total: number; recordings: RecordingInfo[];
  onChange: (s: SceneInfo) => void; onMove: (dir: -1 | 1) => void; onDelete: () => void; onError: (m: string) => void;
}) {
  const [narration, setNarration] = useState(scene.narration);
  const [subtitle, setSubtitle] = useState(scene.subtitle ?? "");
  const [title, setTitle] = useState(scene.title ?? "");
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  useEffect(() => { setNarration(scene.narration); setSubtitle(scene.subtitle ?? ""); setTitle(scene.title ?? ""); }, [scene.id, scene.narration, scene.subtitle, scene.title]);
  useEffect(() => () => { if (audioSrc) URL.revokeObjectURL(audioSrc); }, [audioSrc]);

  async function save(patch: Parameters<typeof api.patchScene>[1]) {
    try { onChange(await api.patchScene(scene.id, patch)); } catch (e) { onError(e instanceof Error ? e.message : "Couldn't save"); }
  }
  const zoom = scene.options.zoom;
  return (
    <Panel className="p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-lg font-semibold">Scene {scene.position}</p>
        <div className="flex gap-1">
          <Button variant="ghost" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up">↑</Button>
          <Button variant="ghost" disabled={index === total - 1} onClick={() => onMove(1)} aria-label="Move down">↓</Button>
          <Button variant="danger" onClick={onDelete}>Delete</Button>
        </div>
      </div>
      <div className="mt-3 space-y-3">
        <Field label="Chapter title"><input className={inputClass} maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} onBlur={() => title !== (scene.title ?? "") && void save({ title })} /></Field>
        <Field label="Narration"><textarea className={`${inputClass} py-2`} rows={3} maxLength={3000} value={narration} onChange={(e) => setNarration(e.target.value)} onBlur={() => narration !== scene.narration && void save({ narration })} /></Field>
        <Field label="Subtitle text (leave empty to use the narration)"><textarea className={`${inputClass} py-2`} rows={2} maxLength={3000} value={subtitle} onChange={(e) => setSubtitle(e.target.value)} onBlur={() => subtitle !== (scene.subtitle ?? "") && void save({ subtitle: subtitle || null })} /></Field>
        <Field label="Footage (real recordings only)">
          <select className={inputClass} value={scene.recording_id ?? ""} onChange={(e) => void save({ recording_id: e.target.value || null })}>
            <option value="">No footage (shows a text card)</option>
            {recordings.map((r) => <option key={r.id} value={r.id}>{r.source_url} · {r.duration_seconds?.toFixed(0) ?? "?"}s · {r.executor}</option>)}
          </select>
        </Field>
        {scene.recording_id && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Start footage at (seconds)"><input className={inputClass} type="number" min={0} step={0.5} defaultValue={scene.options.trim_start ?? 0}
              onBlur={(e) => void save({ options: { ...scene.options, trim_start: Number(e.target.value) || 0 } })} /></Field>
            <label className="flex min-h-11 items-center gap-2 self-end text-sm">
              <input type="checkbox" checked={!!zoom} onChange={(e) => void save({ options: { ...scene.options, zoom: e.target.checked ? { factor: 1.5, cx: 0.5, cy: 0.3 } : undefined } })} />
              Zoom in on this scene
            </label>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {scene.audio ? <Pill tone={scene.audio.up_to_date ? "ok" : "warn"}>{scene.audio.up_to_date ? `Narration audio (${scene.audio.source}, ${scene.audio.duration_seconds?.toFixed(1)}s)` : "Narration changed: audio is out of date"}</Pill> : <Pill tone="mute">No narration audio</Pill>}
          <label className="inline-flex min-h-11 cursor-pointer items-center rounded-lg border border-line px-3 text-sm hover:bg-raised">
            Upload my narration
            <input type="file" accept="audio/*" className="sr-only" onChange={async (e) => {
              const f = e.target.files?.[0]; e.target.value = "";
              if (!f) return;
              try { onChange(await api.uploadAudio(scene.id, f)); } catch (err) { onError(err instanceof Error ? err.message : "Upload failed"); }
            }} />
          </label>
          {scene.audio && <Button variant="ghost" onClick={async () => { try { setAudioSrc(await api.audioUrl(scene.id)); } catch { onError("Couldn't load audio"); } }}>Listen</Button>}
        </div>
        {audioSrc && <audio src={audioSrc} controls className="w-full" />}
      </div>
    </Panel>
  );
}

function MetadataPanel({ scriptId }: { scriptId: string }) {
  const { data, reload } = useApi(() => api.metadata(scriptId), [scriptId]);
  const [form, setForm] = useState({ title: "", description: "", tags: "" });
  const [msg, setMsg] = useState<{ tone: "error" | "info"; text: string } | null>(null);
  useEffect(() => { if (data) setForm({ title: data.metadata.title ?? "", description: data.metadata.description ?? "", tags: (data.metadata.tags ?? []).join(", ") }); }, [data]);
  async function save() {
    try {
      await api.saveMetadata(scriptId, { title: form.title, description: form.description, tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean) });
      setMsg({ tone: "info", text: "Saved." }); await reload();
    } catch (e) { setMsg({ tone: "error", text: e instanceof Error ? e.message : "Couldn't save" }); }
  }
  const v: MetadataView | null = data;
  return (
    <Panel className="p-4">
      <h2 className="text-lg font-semibold">YouTube details</h2>
      <div className="mt-3 space-y-3">
        {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
        <Field label="Title"><input className={inputClass} maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Description"><textarea className={`${inputClass} py-2`} rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Tags (comma separated)"><input className={inputClass} value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
        <Button onClick={() => void save()}>Save details</Button>
        {v?.accuracy_warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
        {v && (
          <>
            <p className="text-sm font-medium">Chapters (from your real timeline)</p>
            <pre className="whitespace-pre-wrap rounded-lg bg-raised p-3 text-xs">{v.chapters_text || "Add scenes to create chapters."}</pre>
            {v.chapter_warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
          </>
        )}
      </div>
    </Panel>
  );
}

export default function ScriptStudio() {
  const projects = useProjects();
  const [projectId, setProjectId] = useProjectId(projects.data);
  const [params, setParams] = useSearchParams();
  const scripts = useApi(() => (projectId ? api.scripts(projectId) : Promise.resolve([])), [projectId]);
  const recordings = useApi(api.recordings);
  const targets = useApi(() => (projectId ? api.targets(projectId) : Promise.resolve([])), [projectId]);
  const voices = useApi(api.voices);
  const scriptId = params.get("script") ?? "";
  const [script, setScript] = useState<ScriptFull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [fromTarget, setFromTarget] = useState("");

  useEffect(() => {
    if (!scriptId) { setScript(null); return; }
    api.script(scriptId).then(setScript).catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the script"));
  }, [scriptId]);

  const open = (id: string) => setParams({ project: projectId, script: id });
  const guard = async (fn: () => Promise<void>) => { setError(null); setNotice(null); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Something went wrong"); } };
  const projectRecs = (recordings.data ?? []).filter((r) => r.project_id === projectId);
  const reloadScript = async () => setScript(await api.script(scriptId));

  if (projects.loading) return <Loading />;
  if (!projects.data?.length) return <Panel><Empty title="Create a project first" hint="Scripts belong to a project." /></Panel>;

  return (
    <>
      <PageHeader title="Script Studio" subtitle="Write scenes, add narration, attach real footage and edit subtitles." />
      {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
      {notice && <div className="mb-4"><Notice tone="info">{notice}</Notice></div>}
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Panel className="space-y-3 p-4">
            <ProjectPicker projects={projects.data} value={projectId} onChange={(id) => setParams({ project: id })} />
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void guard(async () => { const s = await api.createScript(projectId, { title: newTitle, from_target_id: fromTarget || undefined }); setNewTitle(""); await scripts.reload(); open(s.id); }); }}>
              <Field label="New script title"><input className={inputClass} required maxLength={300} value={newTitle} onChange={(e) => setNewTitle(e.target.value)} /></Field>
              <Field label="Start from a research report (optional)">
                <select className={inputClass} value={fromTarget} onChange={(e) => setFromTarget(e.target.value)}>
                  <option value="">Blank script</option>
                  {targets.data?.filter((t) => t.status === "done").map((t) => <option key={t.id} value={t.id}>{t.value}</option>)}
                </select>
              </Field>
              <Button type="submit" className="w-full">Create script</Button>
              {fromTarget && <p className="text-xs text-mute">Creates empty scenes titled from headings seen on the page. You write the narration.</p>}
            </form>
          </Panel>
          <Panel>
            {scripts.data?.length ? (
              <ul className="divide-y divide-line">
                {scripts.data.map((s) => (
                  <li key={s.id}>
                    <button onClick={() => open(s.id)} className={`flex min-h-14 w-full items-center justify-between px-4 text-left text-sm hover:bg-raised ${s.id === scriptId ? "text-accent" : ""}`}>
                      <span className="truncate">{s.title}</span><span className="text-xs text-mute">{s.scene_count} scenes</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : <Empty title="No scripts yet" hint="Create one above." />}
          </Panel>
        </div>

        <div className="space-y-4">
          {!script ? <Panel><Empty title="Pick or create a script" hint="Its scenes will appear here." /></Panel> : (
            <>
              <Panel className="flex flex-wrap items-center gap-2 p-4">
                <Button onClick={() => void guard(async () => { await api.addScene(script.id, { narration: "" }); await reloadScript(); })}>Add scene</Button>
                <Button variant="ghost" onClick={() => void guard(async () => { const t = await api.subtitlesText(script.id, "srt"); const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([t], { type: "text/plain" })); a.download = "subtitles.srt"; a.click(); })}>Download .srt</Button>
                <Button variant="danger" onClick={() => void guard(async () => { if (!window.confirm("Delete this script and its narration?")) return; await api.deleteScript(script.id); setScript(null); setParams({ project: projectId }); await scripts.reload(); })}>Delete script</Button>
              </Panel>
              <Panel className="space-y-3 p-4">
                <h2 className="text-lg font-semibold">Narration voice</h2>
                {voices.data?.map((v) => (
                  <div key={v.name} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span>{v.name} {v.configured ? <Pill tone="ok">ready</Pill> : <Pill tone="mute">needs {v.missing.join(", ")}</Pill>}</span>
                    <Button variant="ghost" disabled={!v.configured} onClick={() => void guard(async () => { await api.generateVoice(script.id, v.name); setNotice("Generating narration in the background. Refresh in a moment."); })}>Generate</Button>
                  </div>
                ))}
                <p className="text-xs text-mute">No voice configured? Upload your own narration audio on each scene below.</p>
                {targets.data?.some((t) => t.status === "done") && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3 text-sm">
                    <span>Draft scenes with AI from</span>
                    <select className="min-h-11 rounded-lg border border-line bg-bg px-2" id="ai-target">{targets.data.filter((t) => t.status === "done").map((t) => <option key={t.id} value={t.id}>{t.value}</option>)}</select>
                    <Button variant="ghost" onClick={() => void guard(async () => { const id = (document.getElementById("ai-target") as HTMLSelectElement).value; setScript(await api.generateAi(script.id, id)); setNotice("AI draft added. Review and edit every scene before use."); })}>Draft</Button>
                  </div>
                )}
              </Panel>
              {script.scenes.length === 0 && <Panel><Empty title="No scenes yet" hint="Add a scene to start." /></Panel>}
              {script.scenes.map((sc, i) => (
                <SceneCard key={sc.id} scene={sc} index={i} total={script.scenes.length} recordings={projectRecs}
                  onChange={(next) => setScript({ ...script, scenes: script.scenes.map((x) => (x.id === next.id ? next : x)) })}
                  onMove={(dir) => void guard(async () => { const order = script.scenes.map((x) => x.id); [order[i], order[i + dir]] = [order[i + dir], order[i]]; setScript(await api.reorderScenes(script.id, order)); })}
                  onDelete={() => void guard(async () => { await api.deleteScene(sc.id); await reloadScript(); })}
                  onError={setError} />
              ))}
              <MetadataPanel scriptId={script.id} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
