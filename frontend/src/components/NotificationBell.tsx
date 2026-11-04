import { Bell } from "lucide-react";
import { useEffect } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function NotificationBell() {
  const { data, reload } = useApi(api.notifications);
  useEffect(() => {
    const id = window.setInterval(() => void reload(), 30000);
    return () => window.clearInterval(id);
  }, [reload]);
  const unread = data?.unread ?? 0;

  return (
    <details className="relative">
      <summary aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative grid size-10 cursor-pointer list-none place-items-center rounded-lg text-mute hover:bg-raised hover:text-ink">
        <Bell className="size-5" aria-hidden />
        {unread > 0 && <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-accent-ink">{unread}</span>}
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-panel shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <p className="text-sm font-semibold">Notifications</p>
          {unread > 0 && <button className="min-h-9 px-2 text-xs text-accent" onClick={async () => { await api.markAllRead(); await reload(); }}>Mark all read</button>}
        </div>
        <ul className="max-h-80 overflow-y-auto">
          {(data?.items ?? []).length === 0 && <li className="p-4 text-sm text-mute">Nothing yet.</li>}
          {data?.items.map((n) => (
            <li key={n.id}>
              <button className={`block min-h-12 w-full px-3 py-2 text-left text-sm hover:bg-raised ${n.read ? "text-mute" : ""}`}
                onClick={async () => { if (!n.read) { await api.markRead(n.id); await reload(); } }}>
                <span className="block font-medium">{n.title}</span>
                {n.body && <span className="block truncate text-xs text-mute">{n.body}</span>}
                <time className="text-[11px] text-mute" dateTime={n.created_at}>{new Date(n.created_at).toLocaleString()}</time>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
