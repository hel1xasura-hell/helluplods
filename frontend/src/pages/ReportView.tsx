import { useEffect, useState } from "react";
import { Loading, Notice, Panel, Pill } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function ReportView({ targetId, onClose }: { targetId: string; onClose: () => void }) {
  const { data, error, loading } = useApi(() => api.report(targetId), [targetId]);
  const [img, setImg] = useState<string | null>(null);
  const shotId = data?.body.screenshot_ids[0];

  useEffect(() => {
    if (!shotId) return;
    let url: string | null = null;
    api.screenshot(shotId).then((u) => { url = u; setImg(u); }).catch(() => setImg(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [shotId]);

  if (loading) return <Loading />;
  if (error || !data) return <Notice tone="error">{error ?? "No report"}</Notice>;
  const r = data.body;

  return (
    <Panel className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-xl font-bold">{r.target_name}</h2>
          <p className="truncate text-sm text-mute">{r.canonical_url}</p>
        </div>
        <button onClick={onClose} className="min-h-11 rounded-lg border border-line px-3 text-sm hover:bg-raised">Close</button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Pill tone={r.tested_hands_on ? "ok" : "warn"}>{r.tested_hands_on ? "Tested hands-on" : "Not tested hands-on"}</Pill>
        <Pill tone="mute">HTTP {r.verification.http_status ?? "?"}</Pill>
        {r.verification.redirected && <Pill tone="warn">Redirected</Pill>}
      </div>

      {r.security_flags.possible_prompt_injection && (
        <div className="mt-3"><Notice tone="warn">This page contains text that looks like instructions to an AI. It was kept as data and not followed.</Notice></div>
      )}
      {r.description && <p className="mt-4 text-sm">{r.description}</p>}
      {img && <img src={img} alt={`Screenshot of ${r.target_name}`} className="mt-4 w-full rounded-lg border border-line" />}

      <h3 className="mt-5 text-base font-semibold">Features seen on the page</h3>
      {r.features.length === 0 ? <p className="text-sm text-mute">None found.</p> : (
        <ul className="mt-2 space-y-1.5 text-sm">
          {r.features.map((f, i) => <li key={i} className="flex items-center justify-between gap-2"><span>{f.name}</span><Pill tone="mute">unverified</Pill></li>)}
        </ul>
      )}

      <h3 className="mt-5 text-base font-semibold">Pages visited ({r.pages_explored.length})</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {r.pages_explored.map((p, i) => <li key={i} className="truncate">{p.title || p.url} <span className="text-mute">· {p.url}</span></li>)}
      </ul>

      {r.pricing.read && (
        <>
          <h3 className="mt-5 text-base font-semibold">Prices seen on the pricing page</h3>
          <p className="mt-2 text-sm">{r.pricing.observed_prices.length ? r.pricing.observed_prices.join(", ") : "No prices found in the text."}</p>
          <p className="mt-1 text-xs text-mute">Unverified: confirm on the live page before using in a video.</p>
        </>
      )}

      {r.tutorial_opportunities.length > 0 && (
        <>
          <h3 className="mt-5 text-base font-semibold">Tutorial ideas</h3>
          <p className="text-xs text-mute">Suggested by AI from the headings above. Not verified.</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{r.tutorial_opportunities.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </>
      )}

      {r.claim_checks.length > 0 && (
        <>
          <h3 className="mt-5 text-base font-semibold">Claim checks</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {r.claim_checks.map((c, i) => (
              <li key={i}><span>{c.claim}</span> <Pill tone={c.status === "corroborated_on_multiple_pages" ? "ok" : "mute"}>{c.status.replace(/_/g, " ")}</Pill></li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-mute">Wording match across visited pages only. It doesn't prove the claim is true.</p>
        </>
      )}

      <h3 className="mt-5 text-base font-semibold">Limitations</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-mute">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>

      <h3 className="mt-5 text-base font-semibold">Sources</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {r.sources.map((s, i) => <li key={i} className="flex items-center justify-between gap-2"><span className="truncate">{s.url}</span><Pill tone={s.official ? "ok" : "mute"}>{s.official ? "official" : "other"}</Pill></li>)}
      </ul>
      <p className="mt-4 text-xs text-mute">Verified {r.verification.verified_at ? new Date(r.verification.verified_at).toLocaleString() : ""}</p>
    </Panel>
  );
}
