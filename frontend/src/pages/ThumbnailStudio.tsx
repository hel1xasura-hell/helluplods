import { useEffect, useState } from "react";
import { ProjectPicker, useProjectId, useProjects } from "../components/ProjectPicker";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { ThumbInfo } from "../types/api";

function Thumb({ t, onSelect, onDelete }: { t: ThumbInfo; onSelect: () => void; onDelete: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null;
    api.thumbnailUrl(t.id).then((x) => { u = x; setSrc(x); }).catch(() => setSrc(null));
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [t.id]);
  return (
    <li className="overflow-hidden rounded-xl border border-line bg-panel">
      {src ? <img src={src} alt={`Thumbnail: ${t.text}`} className="aspect-video w-full object-cover" /> : <div className="aspect-video bg-raised" />}
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2"><p className="truncate text-sm font-medium">{t.text}</p>{t.selected && <Pill tone="ok">selected</Pill>}</div>
        <div className="flex flex-wrap gap-2">
          {!t.selected && <Button variant="ghost" onClick={onSelect}>Use this one</Button>}
          {src && <a href={src} download={`thumbnail-${t.id.slice(0, 6)}.png`} className="inline-flex min-h-11 items-center rounded-lg border border-line px-4 text-sm hover:bg-raised">Export PNG</a>}
          <Button variant="danger" onClick={onDelete}>Delete</Button>
        </div>
      </div>
    </li>
  );
}

export default function ThumbnailStudio() {
  const projects = useProjects();
  const [projectId, setProjectId] = useProjectId(projects.data);
  const thumbs = useApi(() => (projectId ? api.thumbnails(projectId) : Promise.resolve([])), [projectId]);
  const shots = useApi(() => (projectId ? api.screenshots(projectId) : Promise.resolve([])), [projectId]);
  const templates = useApi(api.templates);
  const [form, setForm] = useState({ text: "", template: "bold_left", accent: "#8d6bff", brand: "", screenshot_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { await api.createThumbnail(projectId, { text: form.text, template: form.template, accent: form.accent, brand: form.brand || undefined, screenshot_id: form.screenshot_id || undefined }); await thumbs.reload(); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't create the thumbnail"); }
    finally { setBusy(false); }
  }
  const act = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); await thumbs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "Action failed"); } };

  if (projects.loading) return <Loading />;
  if (!projects.data?.length) return <Panel><Empty title="Create a project first" hint="Thumbnails belong to a project." /></Panel>;

  return (
    <>
      <PageHeader title="Thumbnail Studio" subtitle="Make several versions from a real screenshot, pick one, and export a 1280×720 PNG." />
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <Panel className="h-fit p-4">
          <form className="space-y-3" onSubmit={create}>
            {error && <Notice tone="error">{error}</Notice>}
            <ProjectPicker projects={projects.data} value={projectId} onChange={setProjectId} />
            <Field label="Thumbnail text"><input className={inputClass} required maxLength={80} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} /></Field>
            <Field label="Layout">
              <select className={inputClass} value={form.template} onChange={(e) => setForm({ ...form, template: e.target.value })}>
                {(templates.data ?? ["bold_left"]).map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
              </select>
            </Field>
            <Field label="Background screenshot">
              <select className={inputClass} value={form.screenshot_id} onChange={(e) => setForm({ ...form, screenshot_id: e.target.value })}>
                <option value="">Plain dark background</option>
                {shots.data?.map((s) => <option key={s.id} value={s.id}>{s.url}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Accent colour"><input className={`${inputClass} p-1`} type="color" value={form.accent} onChange={(e) => setForm({ ...form, accent: e.target.value })} /></Field>
              <Field label="Badge (optional)"><input className={inputClass} maxLength={24} value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} /></Field>
            </div>
            <Button type="submit" className="w-full" loading={busy}>Create version</Button>
          </form>
        </Panel>
        <div>
          {thumbs.loading ? <Loading /> : thumbs.data?.length ? (
            <ul className="grid gap-4 sm:grid-cols-2">
              {thumbs.data.map((t) => <Thumb key={t.id} t={t} onSelect={() => void act(() => api.selectThumbnail(t.id))} onDelete={() => void act(() => api.deleteThumbnail(t.id))} />)}
            </ul>
          ) : <Panel><Empty title="No thumbnails yet" hint="Create a few versions and compare them." /></Panel>}
        </div>
      </div>
    </>
  );
}
