import { Loading, Notice, PageHeader, Panel, Pill } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function Agents() {
  const { data, error, loading } = useApi(api.agents);
  if (loading) return <Loading />;
  if (error || !data) return <Notice tone="error">{error ?? "No data"}</Notice>;

  return (
    <>
      <PageHeader title="AI Agents" subtitle="Each agent has a fixed role, a tool allow-list, a timeout and a retry limit. Status is shown as it really is." />
      <div className="grid gap-3 md:grid-cols-2">
        {data.map((a) => (
          <Panel key={a.key} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-semibold">{a.name}</h2>
              <Pill tone={a.implemented ? "ok" : "mute"}>{a.implemented ? "Ready" : `Ships in Stage ${a.stage}`}</Pill>
            </div>
            <p className="mt-1 text-sm text-mute">{a.responsibilities}</p>
            <p className="mt-3 text-xs text-mute">
              Tools: {a.allowed_tools.length ? a.allowed_tools.join(", ") : "none"} · Timeout {a.timeout_seconds}s · Retries {a.max_retries}
            </p>
          </Panel>
        ))}
      </div>
    </>
  );
}
