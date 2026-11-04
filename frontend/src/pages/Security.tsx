import { useState } from "react";
import { Button, Loading, Notice, PageHeader, Panel, Pill } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { useAuth } from "../state/AuthContext";

export default function Security() {
  const { owner } = useAuth();
  const dash = useApi(api.dashboard);
  const integ = useApi(api.integrations);
  const firebase = integ.data?.find((i) => i.key === "firebase");
  const checks = useApi(api.securityChecks);
  const [filter, setFilter] = useState("");
  const audit = useApi(() => api.audit(filter), [filter]);
  const devices = useApi(api.devices);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [devError, setDevError] = useState<string | null>(null);

  async function makeCode() {
    setDevError(null);
    try { setCode(await api.createPairingCode()); }
    catch (e) { setDevError(e instanceof Error ? e.message : "Couldn't create a code"); }
  }
  async function revoke(id: string, name: string) {
    if (!window.confirm(`Revoke "${name}"? It will stop working immediately.`)) return;
    try { await api.revokeDevice(id); await devices.reload(); }
    catch (e) { setDevError(e instanceof Error ? e.message : "Couldn't revoke the device"); }
  }

  return (
    <>
      <PageHeader title="Security Center" subtitle="Who can sign in, which devices are paired, and what has happened recently." />
      <div className="grid gap-3 md:grid-cols-3">
        <Panel className="p-4"><p className="text-sm text-mute">Signed in as</p><p className="mt-1 truncate font-medium">{owner?.email}</p></Panel>
        <Panel className="p-4"><p className="text-sm text-mute">Authentication</p><div className="mt-2"><Pill tone={firebase?.configured ? "ok" : "warn"}>{firebase?.configured ? "Firebase configured" : "Check settings"}</Pill></div></Panel>
        <Panel className="p-4"><p className="text-sm text-mute">Paired local devices</p><p className="mt-1 font-display text-2xl font-bold">{dash.data?.local_workers ?? "–"}</p></Panel>
      </div>
      <Panel className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-lg font-semibold">Paired computers</h2>
          <Button variant="ghost" onClick={() => void makeCode()}>New pairing code</Button>
        </div>
        {devError && <div className="p-4"><Notice tone="error">{devError}</Notice></div>}
        {code && (
          <div className="border-b border-line p-4">
            <p className="text-sm text-mute">Enter this in the companion within 10 minutes. It's shown once and works once.</p>
            <p className="mt-1 font-mono text-2xl font-bold tracking-widest">{code.code}</p>
          </div>
        )}
        <ul className="divide-y divide-line">
          {devices.data?.length === 0 && <li className="p-4 text-sm text-mute">No computers paired yet.</li>}
          {devices.data?.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <div className="min-w-0"><p className="truncate font-medium">{d.name}</p><p className="text-xs text-mute">{d.platform}</p></div>
              <div className="flex shrink-0 items-center gap-2">
                <Pill tone={d.revoked ? "bad" : d.online ? "ok" : "mute"}>{d.revoked ? "revoked" : d.online ? "online" : "offline"}</Pill>
                {!d.revoked && <Button variant="danger" onClick={() => void revoke(d.id, d.name)}>Revoke</Button>}
              </div>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel className="mt-6">
        <h2 className="border-b border-line px-4 py-3 text-lg font-semibold">Configuration checks</h2>
        {checks.loading ? <Loading /> : checks.error ? <div className="p-4"><Notice tone="error">{checks.error}</Notice></div> : (
          <ul className="divide-y divide-line">
            {checks.data?.map((c) => (
              <li key={c.name} className="flex items-start gap-3 px-4 py-3 text-sm">
                <Pill tone={c.status === "pass" ? "ok" : c.status === "warn" ? "warn" : "bad"}>{c.status}</Pill>
                <span><span className="font-medium">{c.name.replace(/_/g, " ")}</span> <span className="text-mute">{c.detail}</span></span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Panel className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-lg font-semibold">Audit trail</h2>
          <select aria-label="Filter audit events" className="min-h-11 rounded-lg border border-line bg-bg px-3 text-sm" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All events</option><option value="auth">Sign-in</option><option value="device">Devices</option><option value="youtube">YouTube</option>
            <option value="approval">Approvals</option><option value="upload">Uploads</option><option value="backup">Backups</option><option value="project">Projects</option>
          </select>
        </div>
        {audit.loading ? <Loading /> : audit.error ? <div className="p-4"><Notice tone="error">{audit.error}</Notice></div> : (
          <ul className="divide-y divide-line">
            {audit.data?.length === 0 && <li className="p-4 text-sm text-mute">No events.</li>}
            {audit.data?.map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2 px-4 py-3 text-sm">
                <span>{a.action}{a.ip ? <span className="text-xs text-mute"> · {a.ip}</span> : null}</span>
                <time className="text-xs text-mute" dateTime={a.at}>{new Date(a.at).toLocaleString()}</time>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
