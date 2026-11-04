import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return {
    ...real,
    api: {
      ...real.api,
      projects: vi.fn(), createProject: vi.fn(), approvals: vi.fn(), youtubeStatus: vi.fn(), approve: vi.fn(),
      thumbnailUrl: vi.fn().mockResolvedValue("blob:x"), renderUrl: vi.fn(), dashboard: vi.fn(),
    },
  };
});
vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({ configured: false, loading: false, owner: null, error: null, signInGoogle: vi.fn(), signInEmail: vi.fn(), signOut: vi.fn() }),
}));

import { BarChart } from "../components/BarChart";
import Approvals from "../pages/Approvals";
import Login from "../pages/Login";
import Overview from "../pages/Overview";
import Projects from "../pages/Projects";
import { api } from "../services/api";

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);
const mocked = <T,>(f: unknown) => f as ReturnType<typeof vi.fn> & T;

beforeEach(() => vi.clearAllMocks());

describe("Login", () => {
  it("explains missing Firebase configuration instead of showing a dead form", () => {
    wrap(<Login />);
    expect(screen.getByText(/Firebase isn't configured/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });
});

describe("Projects form", () => {
  it("creates a project with the chosen settings and clears the form", async () => {
    mocked(api.projects).mockResolvedValue([]);
    mocked(api.createProject).mockResolvedValue({});
    wrap(<Projects />);
    const name = await screen.findByLabelText("Name");
    fireEvent.change(name, { target: { value: "Acme tutorial" } });
    fireEvent.change(screen.getByLabelText("Where browsers run"), { target: { value: "both" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith({ name: "Acme tutorial", description: undefined, execution_mode: "both", publishing_mode: "approval" }));
    await waitFor(() => expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe(""));
  });

  it("shows server errors", async () => {
    mocked(api.projects).mockResolvedValue([]);
    mocked(api.createProject).mockRejectedValue(new Error("Name is too long"));
    wrap(<Projects />);
    fireEvent.change(await screen.findByLabelText("Name"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name is too long");
  });
});

describe("Approvals", () => {
  const ap = {
    id: "a1", status: "pending", note: null, created_at: new Date().toISOString(), script_title: "T",
    render: { id: "r1", duration_seconds: 30, aspect_ratio: "16:9", warnings: [], quality: [{ name: "video_stream", status: "pass", detail: "ok" }] },
    metadata: { title: "Acme tutorial" }, accuracy_warnings: [], uses_ai_voice: true, thumbnail_id: null,
  };
  const yt = { accounts: [{ id: "acc", channel_title: "My Channel", status: "connected" }] };

  it("keeps Approve disabled until kids and AI-content questions are answered, and pre-selects AI disclosure for AI voices", async () => {
    mocked(api.approvals).mockResolvedValue([ap]);
    mocked(api.youtubeStatus).mockResolvedValue(yt);
    wrap(<Approvals />);
    const approve = await screen.findByRole("button", { name: "Approve and upload" });
    expect(approve).toBeDisabled();
    expect(screen.getByLabelText("Yes, disclose it")).toBeChecked();
    fireEvent.click(screen.getByLabelText("No", { selector: "input[name='ka1']" }));
    expect(approve).toBeEnabled();
  });

  it("blocks approval when a quality check failed", async () => {
    mocked(api.approvals).mockResolvedValue([{ ...ap, render: { ...ap.render, quality: [{ name: "audio_stream", status: "fail", detail: "No audio stream" }] } }]);
    mocked(api.youtubeStatus).mockResolvedValue(yt);
    wrap(<Approvals />);
    expect(await screen.findByText(/A quality check failed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve and upload" })).toBeDisabled();
  });

  it("sends explicit answers when approving", async () => {
    mocked(api.approvals).mockResolvedValue([{ ...ap, uses_ai_voice: false }]);
    mocked(api.youtubeStatus).mockResolvedValue(yt);
    mocked(api.approve).mockResolvedValue({ upload_job_id: "j", status: "queued" });
    wrap(<Approvals />);
    await screen.findByRole("button", { name: "Approve and upload" });
    fireEvent.click(screen.getByLabelText("No", { selector: "input[name='ka1']" }));
    fireEvent.click(screen.getByLabelText("No", { selector: "input[name='sa1']" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve and upload" }));
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith("a1", expect.objectContaining({ account_id: "acc", made_for_kids: false, contains_synthetic_media: false, visibility: "private" })));
  });
});

describe("Overview", () => {
  it("shows real counts and the not-connected worker state", async () => {
    mocked(api.dashboard).mockResolvedValue({
      total_projects: 3, research_tasks: 5, active_agents: 0, videos_rendering: 1, videos_awaiting_approval: 2, published_videos: 4, failed_jobs: 0,
      processing_queue: 0, storage_bytes: 2048, cloud_workers: "not_connected", local_workers: 1, recent_activity: [],
    });
    wrap(<Overview />);
    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
  });
});

describe("BarChart", () => {
  it("exposes its data to screen readers", () => {
    render(<BarChart label="Renders per day" data={[{ date: "2026-11-01", count: 2 }, { date: "2026-11-02", count: 0 }]} />);
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("2026-11-01 2"));
  });
});
