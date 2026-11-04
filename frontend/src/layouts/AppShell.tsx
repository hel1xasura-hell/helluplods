import { ChevronsLeft, ChevronsRight, LogOut, MoonStar, Search, Sun, Ellipsis } from "lucide-react";
import { useMemo, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import NotificationBell from "../components/NotificationBell";
import { NAV } from "../nav";
import { useAuth } from "../state/AuthContext";
import { useTheme } from "../state/ThemeContext";

const linkBase = "flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition";

function SidebarLink({ item, collapsed }: { item: (typeof NAV)[number]; collapsed: boolean }) {
  return (
    <NavLink
      to={item.path} end={item.path === "/"} title={item.label}
      className={({ isActive }) => `${linkBase} ${isActive ? "bg-accent/15 text-accent" : "text-mute hover:bg-raised hover:text-ink"}`}
    >
      <item.icon className="size-5 shrink-0" aria-hidden />
      {!collapsed && <span>{item.label}</span>}
    </NavLink>
  );
}

function TopSearch() {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const matches = useMemo(
    () => (q.trim() ? NAV.filter((n) => n.label.toLowerCase().includes(q.trim().toLowerCase())) : []),
    [q],
  );
  return (
    <div className="relative w-full max-w-sm">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-mute" aria-hidden />
      <input
        aria-label="Go to page" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Go to a page"
        onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) { navigate(matches[0].path); setQ(""); } }}
        className="min-h-10 w-full rounded-lg border border-line bg-bg pl-9 pr-3 text-sm placeholder:text-mute focus:border-accent"
      />
      {matches.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-line bg-panel shadow-xl">
          {matches.map((m) => (
            <li key={m.path}>
              <button className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm hover:bg-raised"
                onClick={() => { navigate(m.path); setQ(""); }}>
                <m.icon className="size-4 text-mute" aria-hidden />{m.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const { owner, signOut } = useAuth();
  const { theme, toggle } = useTheme();

  return (
    <div className="flex h-full">
      <aside className={`hidden shrink-0 flex-col border-r border-line bg-panel p-3 md:flex ${collapsed ? "w-[68px]" : "w-60"}`}>
        <div className={`mb-4 flex items-center ${collapsed ? "justify-center" : "justify-between px-2"}`}>
          {!collapsed && <span className="font-display text-lg font-bold tracking-tight">HELL UPLOADS</span>}
          <button aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCollapsed((c) => !c)}
            className="grid size-9 place-items-center rounded-lg text-mute hover:bg-raised hover:text-ink">
            {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
          </button>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-1 overflow-y-auto">
          {NAV.map((item) => <SidebarLink key={item.path} item={item} collapsed={collapsed} />)}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="safe-top flex items-center gap-3 border-b border-line bg-panel px-4 py-2">
          <span className="font-display text-base font-bold md:hidden">HELL UPLOADS</span>
          <div className="ml-auto hidden flex-1 md:block"><TopSearch /></div>
          <div className="ml-auto flex items-center gap-1 md:ml-0">
            <NotificationBell />
            <button aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={toggle}
              className="grid size-10 place-items-center rounded-lg text-mute hover:bg-raised hover:text-ink">
              {theme === "dark" ? <Sun className="size-5" /> : <MoonStar className="size-5" />}
            </button>
            <details className="relative">
              <summary className="grid size-10 cursor-pointer list-none place-items-center rounded-full bg-accent/20 text-sm font-semibold text-accent">
                {(owner?.email ?? "?")[0]?.toUpperCase()}
              </summary>
              <div className="absolute right-0 z-30 mt-2 w-60 rounded-xl border border-line bg-panel p-2 shadow-xl">
                <p className="truncate px-3 py-2 text-xs text-mute">{owner?.email}</p>
                <button onClick={() => void signOut()} className="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-sm hover:bg-raised">
                  <LogOut className="size-4" aria-hidden />Sign out
                </button>
              </div>
            </details>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-6 pb-24 sm:px-8 md:pb-8">
          <div className="mx-auto max-w-6xl"><Outlet /></div>
        </main>

        <nav aria-label="Primary" className="safe-bottom fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-line bg-panel md:hidden">
          {NAV.filter((n) => n.primary).map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"}
              className={({ isActive }) => `flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${isActive ? "text-accent" : "text-mute"}`}>
              <item.icon className="size-5" aria-hidden />{item.label.replace("AI ", "")}
            </NavLink>
          ))}
          <NavLink to="/more" className={({ isActive }) => `flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${isActive ? "text-accent" : "text-mute"}`}>
            <Ellipsis className="size-5" aria-hidden />More
          </NavLink>
        </nav>
      </div>
    </div>
  );
}
