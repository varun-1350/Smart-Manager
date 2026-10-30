import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App.jsx";

const TOKEN = "t".repeat(32);
const DIGEST = "d".repeat(64);

const fake = (status, data) => ({ ok: status < 400, status, json: async () => data });

function installFetch(routes) {
  const calls = [];
  globalThis.fetch = vi.fn((url, init = {}) => {
    const call = {
      url,
      method: init.method || "GET",
      body: init.body ? JSON.parse(init.body) : undefined,
      headers: init.headers,
    };
    calls.push(call);
    const handler = routes[`${call.method} ${url}`];
    return Promise.resolve(handler ? handler(call) : fake(404, { detail: "no route" }));
  });
  return calls;
}

const quiet = {
  "GET /api/interrupted": () => fake(200, { reports: [], errors: [] }),
  "GET /api/undo": () => fake(200, { steps: [] }),
};

async function typeAndSend(text) {
  const input = await screen.findByPlaceholderText(/type a request/i);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
}

beforeEach(() => {
  window.pywebview = { api: { get_token: () => Promise.resolve(TOKEN) } };
});

afterEach(() => {
  cleanup();
  delete window.pywebview;
  vi.restoreAllMocks();
});

describe("App", () => {
  it("approves exactly what the server showed, with the session token", async () => {
    const calls = installFetch({
      ...quiet,
      "POST /api/message": () =>
        fake(200, {
          turn_id: "turn-1",
          kind: "needs_approval",
          message: "Planned changes (1):\n  [HIGH] Move a.pdf -> Archive",
          digest: DIGEST,
          report: null,
        }),
      "POST /api/approve": () =>
        fake(200, {
          turn_id: "turn-2",
          kind: "executed",
          message: "Result: completed\n  [done] Move a.pdf -> Archive",
          digest: "",
          report: { succeeded: true, status: "completed", partial: false, warnings: [] },
        }),
    });
    render(<App />);
    await typeAndSend("move a.pdf to Archive");
    fireEvent.click(await screen.findByRole("button", { name: /approve/i }));
    await screen.findByText(/Result: completed/);

    const sent = calls.find((c) => c.url === "/api/approve");
    expect(sent.body).toEqual({ turn_id: "turn-1", digest: DIGEST });
    expect(sent.headers["X-Session-Token"]).toBe(TOKEN);
  });

  it("shows file names as text and never as HTML", async () => {
    const evil = '<img src=x onerror="alert(1)">.pdf';
    installFetch({
      ...quiet,
      "POST /api/message": () =>
        fake(200, { turn_id: "t", kind: "clarify", message: evil, digest: "", report: null }),
    });
    render(<App />);
    await typeAndSend("anything");
    await screen.findByText(evil);
    expect(document.querySelector("img")).toBeNull();
  });

  it("does not run anything when the request is rejected", async () => {
    const calls = installFetch({
      ...quiet,
      "POST /api/message": () =>
        fake(200, {
          turn_id: "turn-1",
          kind: "needs_approval",
          message: "Planned changes",
          digest: DIGEST,
          report: null,
        }),
      "POST /api/reject": () => fake(200, { ok: true }),
    });
    render(<App />);
    await typeAndSend("delete a.pdf");
    fireEvent.click(await screen.findByRole("button", { name: /reject/i }));
    await screen.findByText(/Rejected/);
    expect(calls.some((c) => c.url === "/api/approve")).toBe(false);
  });
});