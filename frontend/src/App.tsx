import { Navigate, Route, Routes } from "react-router-dom";
import { Loading } from "./components/ui";
import AppShell from "./layouts/AppShell";
import { NAV } from "./nav";
import Agents from "./pages/Agents";
import Analytics from "./pages/Analytics";
import Approvals from "./pages/Approvals";
import BrowserLab from "./pages/BrowserLab";
import Login from "./pages/Login";
import More from "./pages/More";
import Overview from "./pages/Overview";
import Projects from "./pages/Projects";
import Publishing from "./pages/Publishing";
import Recordings from "./pages/Recordings";
import Research from "./pages/Research";
import ScriptStudio from "./pages/ScriptStudio";
import Security from "./pages/Security";
import Settings from "./pages/Settings";
import StagePage from "./pages/StagePage";
import ThumbnailStudio from "./pages/ThumbnailStudio";
import VideoStudio from "./pages/VideoStudio";
import { useAuth } from "./state/AuthContext";

const BUILT: Record<string, JSX.Element> = {
  "/": <Overview />, "/research": <Research />, "/projects": <Projects />,
  "/agents": <Agents />, "/browser-lab": <BrowserLab />, "/recordings": <Recordings />, "/scripts": <ScriptStudio />, "/video": <VideoStudio />, "/thumbnails": <ThumbnailStudio />, "/approvals": <Approvals />, "/analytics": <Analytics />, "/publishing": <Publishing />, "/security": <Security />, "/settings": <Settings />,
};

export default function App() {
  const { loading, owner } = useAuth();
  if (loading) return <Loading />;
  if (!owner) return <Login />;
  return (
    <Routes>
      <Route element={<AppShell />}>
        {NAV.map((n) => <Route key={n.path} path={n.path} element={BUILT[n.path] ?? <StagePage />} />)}
        <Route path="/more" element={<More />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
