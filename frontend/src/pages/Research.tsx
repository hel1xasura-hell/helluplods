import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { TargetKind } from "../types/api";
import ReportView from "./ReportView";

const KINDS: { value: TargetKind; label: string; placeholder: string }[] = [
  { value: "website_url", label: "Website URL", placeholder: "https://example.com" },
  { value: "website_name", label: "Website name", placeholder: "Figma" },
  { value: "android_app", label: "Android app name", placeholder: "Notion" },
  { value: "play_url", label: "Google Play URL", placeholder: "https://play.google.com/store/apps/details?id=…" },
];

export default function Research() {
  const [params, setParams] = useSearchParams();
  const projects = useApi(api.projects);
  const projectId = params.get("project") ?? projects.data?.[0]?.id ?? "";
  const targets = useApi(() => (projectId ? api.targets(projectId) : Promise.resolve([])), [projectId]);
  const [kind, setKind] = useState<TargetKind>("website_url");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openReport, setOpenReport] = useState<string | null>(null);

  const inProgress = targets.data?.some((t) => t.status === "queued" || t.status === "running") ?? false;
  useEffect(() => {
    if (!inProgress) return;
    const id = window.setInterval(() => void targets.reload(), 3000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inProgress, projectId]);

  const [notice, setNotice] = useState<string | null>(null);
  async function record(targetId: string) {
    setError(null); setNotice(null);
    try {
      const r = await api.recordTarget(targetId);
      setNotice(r.executor === "local" ? "Recording queued for your paired computer. It starts when the companion picks it up." : "Recording started in the cloud. Find it under Recordings.");
    } catch (err) { setError(err instanceof Error ? err.message : "Couldn't start recording"); }
  }

  async function run(targetId: string) {
    setError(null);
    try { await api.startResearch(targetId); await targets.reload(); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't start research"); }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await api.addTarget(projectId, { kind, value }); setValue(""); await targets.reload(); }
    catch (err) { setError(err instanceof Error ? err.message : "Couldn't add the target"); }
    finally { setBusy(false); }
  }

  if (projects.loading) return <Loading />;
  if (projects.error) return <Notice tone="error">{projects.error}</Notice>;

  return (
    <>
      <PageHeader title="AI Research" subtitle="Add sites and apps, then run research. Reports list only what was actually seen on the page; features stay unverified until a workflow is exercised." />
      {!projects.data?.length ? (
        <Panel><Empty title="Create a project first" hint="Research targets belong to a project. Add one on the Projects page." /></Panel>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
          <Panel className="h-fit p-4">
            <form className="space-y-3" onSubmit={add}>
              {error && <Notice tone="error">{error}</Notice>}
              {notice && <Notice tone="info">{notice}</Notice>}
              <Field label="Project">
                <select className={inputClass} value={projectId} onChange={(e) => setParams({ project: e.target.value })}>
                  {projects.data.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Target type">
                <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value as TargetKind)}>
                  {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
                </select>
              </Field>
              <Field label="Target">
                <input className={inputClass} required maxLength={2048} value={value} onChange={(e) => setValue(e.target.value)}
                  placeholder={KINDS.find((k) => k.value === kind)?.placeholder} />
              </Field>
              <Button type="submit" className="w-full" loading={busy}>Add target</Button>
              <p className="text-xs text-mute">Local and private addresses are rejected for safety.</p>
            </form>
          </Panel>

          <div className="space-y-4">
          {openReport && <ReportView targetId={openReport} onClose={() => setOpenReport(null)} />}
          <Panel>
            {targets.loading ? <Loading /> : targets.data && targets.data.length > 0 ? (
              <ul className="divide-y divide-line">
                {targets.data.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3 p-4">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{t.value}</p>
                      <p className="text-xs text-mute">{KINDS.find((k) => k.value === t.kind)?.label}</p>
                      {t.error && <p className="mt-1 text-xs text-warn">{t.error}</p>}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Pill tone={t.status === "done" ? "ok" : t.status === "failed" || t.status === "needs_url" ? "warn" : "mute"}>
                        {t.status === "needs_url" ? "needs official URL" : t.status}
                      </Pill>
                      {t.status === "done" && <Button variant="ghost" onClick={() => setOpenReport(t.id)}>Report</Button>}
                      {(t.kind === "website_url" || t.kind === "play_url") && <Button variant="ghost" onClick={() => void record(t.id)}>Record</Button>}
                      {t.status !== "queued" && t.status !== "running" && (
                        <Button variant="ghost" onClick={() => void run(t.id)}>{t.status === "pending" ? "Research" : "Run again"}</Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : <Empty title="No targets yet" hint="Add a website or app to this project." />}
          </Panel>
          </div>
        </div>
      )}
    </>
  );
}
