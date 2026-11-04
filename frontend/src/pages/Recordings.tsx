import { useEffect, useState } from "react";
import { Empty, Loading, Notice, PageHeader, Panel, Pill } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { RecordingInfo } from "../types/api";

function Player({ rec }: { rec: RecordingInfo }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    api.recordingUrl(rec.id).then((u) => { url = u; setSrc(u); }).catch(() => setErr(true));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [rec.id]);
  if (err) return <Notice tone="error">Couldn't load the video.</Notice>;
  if (!src) return <Loading />;
  return <video src={src} controls className="w-full rounded-lg border border-line bg-black" />;
}

export default function Recordings() {
  const recs = useApi(api.recordings);
  const tasks = useApi(api.recordingTasks);
  const [open, setOpen] = useState<string | null>(null);
  const pending = tasks.data?.some((t) => t.status === "queued" || t.status === "claimed") ?? false;

  useEffect(() => {
    if (!pending) return;
    const id = window.setInterval(() => { void tasks.reload(); void recs.reload(); }, 3000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  return (
    <>
      <PageHeader title="Recordings" subtitle="Real captures of real browser sessions, from the cloud or a paired computer. Nothing here is generated." />
      {(tasks.data ?? []).filter((t) => t.status !== "done").length > 0 && (
        <Panel className="mb-4">
          <h2 className="border-b border-line px-4 py-3 text-base font-semibold">Recording jobs</h2>
          <ul className="divide-y divide-line">
            {tasks.data!.filter((t) => t.status !== "done").map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="min-w-0"><p className="truncate">{t.url}</p>{t.error && <p className="text-xs text-warn">{t.error}</p>}</div>
                <div className="flex shrink-0 gap-2"><Pill tone="mute">{t.executor === "local" ? "your computer" : "cloud"}</Pill><Pill tone={t.status === "failed" ? "bad" : "warn"}>{t.status}</Pill></div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel>
        {recs.loading ? <Loading /> : recs.error ? <div className="p-4"><Notice tone="error">{recs.error}</Notice></div> :
          recs.data && recs.data.length > 0 ? (
            <ul className="divide-y divide-line">
              {recs.data.map((r) => (
                <li key={r.id} className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{r.source_url}</p>
                      <p className="text-xs text-mute">{r.duration_seconds ? `${r.duration_seconds.toFixed(1)} s` : "duration unknown"} · {r.width}×{r.height} · {new Date(r.created_at).toLocaleString()}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Pill tone="ok">real capture</Pill><Pill tone="mute">{r.executor === "local" ? "your computer" : "cloud"}</Pill>
                      <button className="min-h-11 rounded-lg border border-line px-3 text-sm hover:bg-raised" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide" : "Play"}</button>
                    </div>
                  </div>
                  {open === r.id && <div className="mt-3"><Player rec={r} /></div>}
                </li>
              ))}
            </ul>
          ) : <Empty title="No recordings yet" hint="Open AI Research and press Record on a website target." />}
      </Panel>
    </>
  );
}
