import { useEffect, useRef, useState } from "react";
import { api, getToken, wsBase } from "../services/api";
import type { RunInfo } from "../types/api";

/** Live runs over WebSocket (token sent as first message). Falls back to polling if the socket can't connect. */
export function useLiveRuns() {
  const [runs, setRuns] = useState<RunInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    let closed = false;
    let ws: WebSocket | null = null;

    const poll = async () => {
      try { setRuns(await api.runs()); setError(null); }
      catch (e) { setError(e instanceof Error ? e.message : "Couldn't load runs"); }
    };
    const startPolling = () => {
      if (pollTimer.current !== null || closed) return;
      void poll();
      pollTimer.current = window.setInterval(() => void poll(), 3000);
    };

    (async () => {
      const token = await getToken();
      if (!token || typeof WebSocket === "undefined") return startPolling();
      ws = new WebSocket(`${wsBase()}/ws/runs`);
      ws.onopen = () => ws?.send(JSON.stringify({ token }));
      ws.onmessage = (ev) => { setLive(true); setError(null); setRuns((JSON.parse(ev.data) as { runs: RunInfo[] }).runs); };
      ws.onclose = () => { setLive(false); if (!closed) startPolling(); };
      ws.onerror = () => ws?.close();
    })();

    return () => {
      closed = true;
      ws?.close();
      if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    };
  }, []);

  return { runs, error, live, refresh: async () => setRuns(await api.runs()) };
}
