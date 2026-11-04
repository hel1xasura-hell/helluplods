import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NAV } from "../nav";
import StagePage from "../pages/StagePage";
import { ApiError, api, setTokenProvider } from "../services/api";

describe("navigation", () => {
  it("has the 15 required sections, each with a purpose", () => {
    expect(NAV).toHaveLength(15);
    expect(NAV.every((n) => n.purpose.length > 0)).toBe(true);
    expect(new Set(NAV.map((n) => n.path)).size).toBe(15);
  });
  it("shows four primary items for the mobile bottom bar", () => {
    expect(NAV.filter((n) => n.primary)).toHaveLength(4);
  });
});

describe("StagePage", () => {
  it("states honestly that the section is not built", () => {
    render(<MemoryRouter initialEntries={["/video"]}><StagePage /></MemoryRouter>);
    expect(screen.getByText("Video Studio")).toBeInTheDocument();
    expect(screen.getByText("Not built yet")).toBeInTheDocument();
  });
});

describe("api client", () => {
  it("sends the bearer token and surfaces server errors", async () => {
    setTokenProvider(async () => "tok");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid token" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.me()).rejects.toMatchObject({ status: 401, message: "Invalid token" });
    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok");
    vi.unstubAllGlobals();
  });
  it("reports an unreachable server clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(api.projects()).rejects.toBeInstanceOf(ApiError);
    vi.unstubAllGlobals();
  });
});
