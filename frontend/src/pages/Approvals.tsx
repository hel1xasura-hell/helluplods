import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Empty, Field, Loading, Notice, PageHeader, Panel, Pill, inputClass } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { ApprovalInfo } from "../types/api";

const qTone = (s: string) => (s === "pass" ? "ok" : s === "fail" ? "bad" : "warn") as "ok" | "bad" | "warn";

function ApprovalCard({ ap, accounts, onDone }: { ap: ApprovalInfo; accounts: { id: string; channel_title: string | null }[]; onDone: () => void }) {
  const [video, setVideo] = useState<string | null>(null);
  const [thumb, setThumb] = useState<string | null>(null);
  const [account, setAccount] = useState(accounts[0]?.id ?? "");
  const [visibility, setVisibility] = useState("private");
  const [schedule, setSchedule] = useState("");
  const [kids, setKids] = useState<"" | "yes" | "no">("");
  const [synthetic, setSynthetic] = useState<"" | "yes" | "no">(ap.uses_ai_voice ? "yes" : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => () => { if (video) URL.revokeObjectURL(video); if (thumb) URL.revokeObjectURL(thumb); }, [video, thumb]);
  useEffect(() => { if (ap.thumbnail_id) api.thumbnailUrl(ap.thumbnail_id).then(setThumb).catch(() => undefined); }, [ap.thumbnail_id]);
  const fails = ap.render?.quality.some((c) => c.status === "fail");

  async function approve() {
    setBusy(true); setError(null);
    try {
      await api.approve(ap.id, {
        account_id: account, visibility, publish_at: schedule ? new Date(schedule).toISOString() : null,
        made_for_kids: kids === "yes", contains_synthetic_media: synthetic === "yes",
      });
      onDone();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't approve"); }
    finally { setBusy(false); }
  }

  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold">{ap.metadata.title || ap.script_title || "Untitled video"}</h2>
          <p className="text-xs text-mute">{ap.render?.aspect_ratio} · {ap.render?.duration_seconds?.toFixed(0) ?? "?"}s · {new Date(ap.created_at).toLocaleString()}</p>
        </div>
        {ap.note && <Pill tone="warn">needs review</Pill>}
      </div>
      {ap.note && <div className="mt-3"><Notice tone="warn">{ap.note}</Notice></div>}
      {thumb && <img src={thumb} alt="Selected thumbnail" className="mt-3 aspect-video w-full max-w-xs rounded-lg border border-line object-cover" />}
      {ap.metadata.description && <p className="mt-3 whitespace-pre-wrap text-sm">{ap.metadata.description}</p>}

      <h3 className="mt-4 text-base font-semibold">Quality checks</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {ap.render?.quality.map((c) => <li key={c.name} className="flex items-start gap-2"><Pill tone={qTone(c.status)}>{c.status}</Pill><span className="text-mute">{c.detail}</span></li>)}
      </ul>
      {ap.accuracy_warnings.map((w, i) => <p key={i} className="mt-1 text-xs text-warn">{w}</p>)}
      {ap.render?.warnings.map((w, i) => <p key={i} className="mt-1 text-xs text-warn">{w}</p>)}

      <div className="mt-3">
        {!video ? <Button variant="ghost" onClick={async () => { try { setVideo(await api.renderUrl(ap.render!.id)); } catch { setError("Couldn't load the video"); } }}>Watch the video</Button>
          : <video src={video} controls className="w-full max-w-xl rounded-lg border border-line bg-black" />}
      </div>

      <div className="mt-5 space-y-3 border-t border-line pt-4">
        {error && <Notice tone="error">{error}</Notice>}
        {fails && <Notice tone="error">A quality check failed. Fix the problem and render again before approving.</Notice>}
        {accounts.length === 0 && <Notice tone="warn">Connect a YouTube channel on the <Link className="underline" to="/publishing">Publishing</Link> page first.</Notice>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Channel"><select className={inputClass} value={account} onChange={(e) => setAccount(e.target.value)}>{accounts.map((a) => <option key={a.id} value={a.id}>{a.channel_title}</option>)}</select></Field>
          <Field label="Visibility"><select className={inputClass} value={visibility} onChange={(e) => setVisibility(e.target.value)}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></Field>
          <Field label="Publish at (optional, your local time)"><input className={inputClass} type="datetime-local" value={schedule} onChange={(e) => setSchedule(e.target.value)} /></Field>
        </div>
        <fieldset className="text-sm"><legend className="mb-1 font-medium">Is this video made for kids?</legend>
          <label className="mr-4 inline-flex min-h-11 items-center gap-2"><input type="radio" name={`k${ap.id}`} checked={kids === "no"} onChange={() => setKids("no")} />No</label>
          <label className="inline-flex min-h-11 items-center gap-2"><input type="radio" name={`k${ap.id}`} checked={kids === "yes"} onChange={() => setKids("yes")} />Yes</label>
        </fieldset>
        <fieldset className="text-sm"><legend className="mb-1 font-medium">Does it contain realistic AI-generated or altered content (such as an AI voice)?</legend>
          <label className="mr-4 inline-flex min-h-11 items-center gap-2"><input type="radio" name={`s${ap.id}`} checked={synthetic === "yes"} onChange={() => setSynthetic("yes")} />Yes, disclose it</label>
          <label className="inline-flex min-h-11 items-center gap-2"><input type="radio" name={`s${ap.id}`} checked={synthetic === "no"} onChange={() => setSynthetic("no")} />No</label>
          {ap.uses_ai_voice && <p className="text-xs text-warn">This video uses an AI voice, so disclosure is required.</p>}
        </fieldset>
        {schedule && <p className="text-xs text-mute">Scheduled videos upload as private and YouTube publishes them at that time.</p>}
        <div className="flex flex-wrap gap-2">
          <Button loading={busy} disabled={!account || !kids || !synthetic || !!fails} onClick={() => void approve()}>Approve and upload</Button>
          <Button variant="danger" onClick={async () => { const note = window.prompt("Why reject it? (optional)") ?? ""; try { await api.reject(ap.id, note); onDone(); } catch (e) { setError(e instanceof Error ? e.message : "Couldn't reject"); } }}>Reject</Button>
        </div>
      </div>
    </Panel>
  );
}

export default function Approvals() {
  const list = useApi(api.approvals);
  const yt = useApi(api.youtubeStatus);
  if (list.loading || yt.loading) return <Loading />;
  if (list.error) return <Notice tone="error">{list.error}</Notice>;
  const pending = (list.data ?? []).filter((a) => a.status === "pending");
  const history = (list.data ?? []).filter((a) => a.status !== "pending");
  const accounts = (yt.data?.accounts ?? []).filter((a) => a.status === "connected");
  return (
    <>
      <PageHeader title="Approvals" subtitle="Nothing is uploaded until you approve it here. Review the checks, then choose how it goes out." />
      {pending.length === 0 ? <Panel><Empty title="Nothing waiting" hint="Finished renders appear here for review." /></Panel> : (
        <div className="space-y-4">{pending.map((a) => <ApprovalCard key={a.id} ap={a} accounts={accounts} onDone={() => void list.reload()} />)}</div>
      )}
      {history.length > 0 && (
        <Panel className="mt-6">
          <h2 className="border-b border-line px-4 py-3 text-lg font-semibold">History</h2>
          <ul className="divide-y divide-line">
            {history.map((a) => <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm"><span className="truncate">{a.metadata.title || a.script_title}</span><Pill tone={a.status === "rejected" ? "bad" : "ok"}>{a.status.replace("_", " ")}</Pill></li>)}
          </ul>
        </Panel>
      )}
    </>
  );
}
