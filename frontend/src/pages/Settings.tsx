import { Check, X } from "lucide-react";
import { useState } from "react";
import { Button, Loading, Notice, PageHeader, Panel, Pill, formatBytes } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { useTheme } from "../state/ThemeContext";

export default function Settings() {
  const { theme, toggle } = useTheme();
  const { data, error, loading } = useApi(api.integrations);
  const health = useApi(api.health);
  const backups = useApi(api.backups);
  const [msg, setMsg] = useState<{ tone: "error" | "info"; text: string } | null>(null);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setMsg(null); try { await fn(); setMsg({ tone: "info", text: ok }); } catch (e) { setMsg({ tone: "error", text: e instanceof Error ? e.message : "Failed" }); } };
  return (
    <>
      <PageHeader title="Settings" subtitle="Appearance and the status of every external service." />
      <Panel className="mb-6 flex items-center justify-between p-4">
        <div><p className="font-medium">Theme</p><p className="text-sm text-mute">Currently {theme}.</p></div>
        <button onClick={toggle} className="min-h-11 rounded-lg border border-line px-4 text-sm hover:bg-raised">Switch to {theme === "dark" ? "light" : "dark"}</button>
      </Panel>
      {msg && <div className="mb-4"><Notice tone={msg.tone}>{msg.text}</Notice></div>}
      <Panel className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-lg font-semibold">System health</h2>
          {health.data && <Pill tone={health.data.overall === "ok" ? "ok" : "warn"}>{health.data.overall}</Pill>}
        </div>
        {health.loading ? <Loading /> : health.error || !health.data ? <div className="p-4"><Notice tone="error">{health.error ?? "No data"}</Notice></div> : (
          <div className="space-y-3 p-4 text-sm">
            <ul className="grid gap-2 sm:grid-cols-2">{health.data.components.map((c) => <li key={c.name} className="flex items-center gap-2"><Pill tone={c.status === "ok" ? "ok" : "bad"}>{c.status}</Pill><span>{c.name}</span><span className="truncate text-xs text-mute">{c.detail}</span></li>)}</ul>
            <p className="text-mute">Workers online: {health.data.workers_online.join(", ") || "none"} · Queued: {Object.entries(health.data.queue_depth).map(([q, n]) => `${q} ${n}`).join(", ") || "n/a"} · Storage {formatBytes(health.data.storage_bytes)}</p>
            {Object.values(health.data.stuck).some((n) => n > 0) && (
              <Notice tone="warn">Stuck work: {Object.entries(health.data.stuck).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(", ")}. <button className="underline" onClick={() => void run(async () => { await api.recoverStuck(); await health.reload(); }, "Stuck work was marked failed so you can retry it.")}>Recover now</button></Notice>
            )}
          </div>
        )}
      </Panel>
      <Panel className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-lg font-semibold">Database backups</h2>
          <Button variant="ghost" disabled={!backups.data?.database_is_postgres || !backups.data?.pg_dump_available} onClick={() => void run(async () => { await api.createBackup(); }, "Backup started. Refresh in a moment.")}>Back up now</Button>
        </div>
        <div className="p-4 text-sm">
          {backups.data && !backups.data.database_is_postgres && <Notice tone="info">Backups need PostgreSQL. This environment uses a different database.</Notice>}
          {backups.data && backups.data.database_is_postgres && !backups.data.pg_dump_available && <Notice tone="warn">pg_dump isn't installed here, so backups can only run on the worker container.</Notice>}
          <ul className="mt-2 divide-y divide-line">
            {backups.data?.items.length === 0 && <li className="py-2 text-mute">No backups yet. A nightly backup runs automatically on the worker.</li>}
            {backups.data?.items.map((b) => <li key={b.id} className="flex justify-between gap-2 py-2"><span>{new Date(b.created_at).toLocaleString()}</span><span className="text-mute">{formatBytes(b.size_bytes)}</span></li>)}
          </ul>
        </div>
      </Panel>
      <h2 className="mb-3 text-lg font-semibold">Integrations</h2>
      {loading ? <Loading /> : error || !data ? <Notice tone="error">{error ?? "No data"}</Notice> : (
        <div className="space-y-3">
          {data.map((i) => (
            <Panel key={i.key} className="p-4">
              <div className="flex items-center gap-2">
                {i.configured ? <Check className="size-4 text-ok" aria-hidden /> : <X className="size-4 text-bad" aria-hidden />}
                <p className="font-medium">{i.label}</p>
                <span className="text-sm text-mute">{i.configured ? "Configured" : "Not configured"}</span>
              </div>
              <p className="mt-1 text-sm text-mute">Used for: {i.needed_for}</p>
              {!i.configured && (
                <div className="mt-2 text-sm">
                  <p>Missing: <code className="text-warn">{i.missing.join(", ")}</code></p>
                  {i.local_alternative && <p className="mt-1 text-mute">Meanwhile: {i.local_alternative}</p>}
                </div>
              )}
            </Panel>
          ))}
        </div>
      )}
    </>
  );
}
