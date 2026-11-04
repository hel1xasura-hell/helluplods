import { useState } from "react";
import { Button, Empty, Loading, Notice, PageHeader, Panel, Pill } from "../components/ui";
import { useLiveRuns } from "../hooks/useLiveRuns";
import { api } from "../services/api";
import type { RunInfo } from "../types/api";

const tone = (s: string) =>
  (s === "succeeded" ? "ok" : s === "failed" ? "bad" : s === "running" || s === "paused" ? "warn" : "mute") as "ok" | "bad" | "warn" | "mute";
const active = (r: RunInfo) => ["queued", "running", "paused"].includes(r.status);

export default function BrowserLab() {
  const { runs, error, live, refresh } = useLiveRuns();
  const [actionError, setActionError] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try { await fn(); await refresh(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Action failed"); }
  }

  return (
    <>
      <PageHeader title="Browser Lab" subtitle="Watch automated browser runs and pause, resume or stop them."
        action={<Pill tone={live ? "ok" : "mute"}>{live ? "Live" : "Polling"}</Pill>} />
      <div className="mb-4"><Notice tone="info">Controls act between pages: a pause or stop takes effect once the page being loaded finishes. Local-device sessions arrive with the desktop companion.</Notice></div>
      {actionError && <div className="mb-4"><Notice tone="error">{actionError}</Notice></div>}
      <Panel>
        {!runs && !error ? <Loading /> : error && !runs ? <div className="p-4"><Notice tone="error">{error}</Notice></div> :
          runs && runs.length > 0 ? (
            <ul className="divide-y divide-line">
              {runs.map((r) => (
                <li key={r.id} className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate font-medium">{r.target?.value ?? r.agent_key}</p>
                    <Pill tone={tone(r.status)}>{r.control && active(r) ? `${r.control} requested` : r.status.replace("_", " ")}</Pill>
                  </div>
                  {r.current_url && <p className="mt-1 truncate text-xs text-mute">Current page: {r.current_url}</p>}
                  {active(r) && (
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={Math.round(r.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
                      <div className="h-full bg-accent transition-all" style={{ width: `${Math.round(r.progress * 100)}%` }} />
                    </div>
                  )}
                  {r.error && <p className="mt-1 text-xs text-warn">{r.error}</p>}
                  {active(r) && (
                    <div className="mt-3 flex gap-2">
                      {r.status === "paused" || r.control === "pause"
                        ? <Button variant="ghost" onClick={() => void act(() => api.resumeRun(r.id))}>Resume</Button>
                        : <Button variant="ghost" onClick={() => void act(() => api.pauseRun(r.id))}>Pause</Button>}
                      <Button variant="danger" onClick={() => void act(() => api.stopRun(r.id))}>Stop</Button>
                    </div>
                  )}
                  <p className="mt-2 text-xs text-mute">{r.started_at ? new Date(r.started_at).toLocaleString() : "Not started"}</p>
                </li>
              ))}
            </ul>
          ) : <Empty title="No runs yet" hint="Run research on a target and it will show up here." />}
      </Panel>
    </>
  );
}
