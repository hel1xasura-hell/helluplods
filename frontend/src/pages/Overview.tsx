import { api } from "../services/api";
import { Empty, Loading, Notice, PageHeader, Panel, Pill, formatBytes } from "../components/ui";
import { useApi } from "../hooks/useApi";

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Panel className="p-4">
      <p className="text-sm text-mute">{label}</p>
      <p className="mt-1 font-display text-3xl font-bold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-mute">{hint}</p>}
    </Panel>
  );
}

export default function Overview() {
  const { data, error, loading } = useApi(api.dashboard);
  if (loading) return <Loading />;
  if (error || !data) return <Notice tone="error">{error ?? "No data"}</Notice>;

  return (
    <>
      <PageHeader title="Overview" subtitle="Everything below is counted from your own records." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Projects" value={data.total_projects} />
        <Stat label="Research targets" value={data.research_tasks} />
        <Stat label="Active agents" value={data.active_agents} />
        <Stat label="Videos rendering" value={data.videos_rendering} />
        <Stat label="Awaiting approval" value={data.videos_awaiting_approval} />
        <Stat label="Published" value={data.published_videos} />
        <Stat label="Failed jobs" value={data.failed_jobs} />
        <Stat label="Queued" value={data.processing_queue} />
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <Panel className="p-4">
          <p className="text-sm text-mute">Storage used</p>
          <p className="mt-1 font-display text-2xl font-bold">{formatBytes(data.storage_bytes)}</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-sm text-mute">Cloud workers</p>
          <div className="mt-2"><Pill tone={data.cloud_workers === "online" ? "ok" : "mute"}>{data.cloud_workers === "online" ? "Online" : "Not connected"}</Pill></div>
          <p className="mt-2 text-xs text-mute">Worker heartbeats arrive with Stage 2.</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-sm text-mute">Local workers paired</p>
          <p className="mt-1 font-display text-2xl font-bold">{data.local_workers}</p>
        </Panel>
      </div>

      <Panel className="mt-6">
        <h2 className="border-b border-line px-4 py-3 text-lg font-semibold">Recent activity</h2>
        {data.recent_activity.length === 0 ? (
          <Empty title="No activity yet" hint="Create a project and activity will appear here." />
        ) : (
          <ul className="divide-y divide-line">
            {data.recent_activity.map((a, i) => (
              <li key={i} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <span>{a.action.replace(/[._]/g, " ")}</span>
                <time className="text-xs text-mute" dateTime={a.at}>{new Date(a.at).toLocaleString()}</time>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
