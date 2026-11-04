import {
  BarChart3, Bot, CheckCircle2, FlaskConical, FolderKanban, Globe, Image, Library, LayoutDashboard,
  Radio, Send, Settings, ShieldCheck, Film, ScrollText, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string; label: string; icon: LucideIcon; stage: number; primary?: boolean;
  purpose: string; // used by pages that are not built yet
}

export const NAV: NavItem[] = [
  { path: "/", label: "Overview", icon: LayoutDashboard, stage: 1, primary: true, purpose: "Live counts from your records." },
  { path: "/research", label: "AI Research", icon: FlaskConical, stage: 2, primary: true, purpose: "Submit sites and apps for research." },
  { path: "/projects", label: "Projects", icon: FolderKanban, stage: 1, primary: true, purpose: "Create and manage tutorial projects." },
  { path: "/agents", label: "AI Agents", icon: Bot, stage: 2, primary: true, purpose: "See each agent's role, limits and status." },
  { path: "/browser-lab", label: "Browser Lab", icon: Globe, stage: 2, purpose: "Start, pause and watch cloud or local browser sessions." },
  { path: "/recordings", label: "Recordings", icon: Radio, stage: 3, purpose: "Review real screen recordings captured for each project." },
  { path: "/scripts", label: "Script Studio", icon: ScrollText, stage: 4, purpose: "Edit tutorial scripts, narration and subtitles." },
  { path: "/video", label: "Video Studio", icon: Film, stage: 4, purpose: "Review scenes, replace footage and render again." },
  { path: "/thumbnails", label: "Thumbnail Studio", icon: Image, stage: 4, purpose: "Create, edit and export thumbnail versions." },
  { path: "/media", label: "Media Library", icon: Library, stage: 3, purpose: "Browse every screenshot, recording, audio and video file." },
  { path: "/approvals", label: "Approvals", icon: CheckCircle2, stage: 5, purpose: "Approve or reject finished videos before upload." },
  { path: "/publishing", label: "Publishing", icon: Send, stage: 5, purpose: "Connect YouTube, schedule uploads and view history." },
  { path: "/analytics", label: "Analytics", icon: BarChart3, stage: 6, purpose: "Track video performance and production throughput." },
  { path: "/security", label: "Security Center", icon: ShieldCheck, stage: 1, purpose: "Review access, devices and audit activity." },
  { path: "/settings", label: "Settings", icon: Settings, stage: 1, purpose: "Appearance and integration status." },
];
