import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

class TestIntersectionObserver {
  static observers: TestIntersectionObserver[] = [];
  constructor(private callback: IntersectionObserverCallback) { TestIntersectionObserver.observers.push(this); }
  observe() {}
  disconnect() {}
  unobserve() {}
  trigger() {
    this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  static latest() { return this.observers[this.observers.length - 1]; }
}

const catalogs = { offers: [{ id: 18001, name: "Offer One" }], domains: [{ id: 1813, name: "tracker.example" }], groups: [{ id: 10332, name: "FORTESTS" }], traffic_sources: [{ id: 836, name: "FORTESTS" }] };

describe("Adrobot workspace", () => {
  it("opens on campaign creation and loads campaigns independently of catalogs", async () => {
    let resolveCatalog!: (response: Response) => void;
    const catalogRequest = new Promise<Response>((resolve) => { resolveCatalog = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/catalogs")) return catalogRequest;
      return Promise.resolve(new Response(JSON.stringify({ items: [{ id: 165, name: "campaign_165" }] }), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Новая кампания" })).toBeInTheDocument();
    expect(await screen.findByText("campaign_165")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Новая кампания" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/campaigns?offset=0&limit=10", expect.any(Object));

    resolveCatalog(new Response(JSON.stringify(catalogs), { status: 200 }));
  });

  it("loads the next batch of 10 when the list sentinel becomes visible", async () => {
    const firstBatch = Array.from({ length: 10 }, (_, index) => ({ id: 120 - index, name: `campaign_${120 - index}` }));
    const secondBatch = Array.from({ length: 10 }, (_, index) => ({ id: 110 - index, name: `campaign_${110 - index}` }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/catalogs")) return new Response(JSON.stringify(catalogs), { status: 200 });
      const items = url.includes("offset=10") ? secondBatch : firstBatch;
      return new Response(JSON.stringify({ items }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);

    render(<App />);
    expect(await screen.findByText("campaign_120")).toBeInTheDocument();
    expect(screen.queryByText("campaign_110")).not.toBeInTheDocument();

    TestIntersectionObserver.latest().trigger();
    expect(await screen.findByText("campaign_110")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/campaigns?offset=10&limit=10", expect.any(Object));
  });

  it("opens the global operations history from the header", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/catalogs") ? catalogs : url.includes("/history?")
        ? { items: [], total: 0, has_more: false }
        : { items: [] };
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "История операций" }));

    expect(await screen.findByRole("heading", { name: "История операций" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/history?"), expect.any(Object));
  });
});
