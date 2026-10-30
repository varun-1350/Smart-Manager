import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HistoryPanel, SettingsPanel } from "./panels.jsx";

const fake = (status, data) => ({ ok: status < 400, status, json: async () => data });

function installFetch(routes) {
  const calls = [];
  globalThis.fetch = vi.fn((url, init = {}) => {
    const call = {
      url,
      method: init.method || "GET",
      body: init.body ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    const handler = routes[`${call.method} ${url}`];
    return Promise.resolve(handler ? handler(call) : fake(404, { detail: "no route" }));
  });
  return calls;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const EVIL = '<img src=x onerror="alert(1)">.pdf';
const item = {
  id: 7,
  created_at: "2026-10-30T10:00:00+00:00",
  request: EVIL,
  kind: "executed",
  status: "completed",
  preview: "Result: completed",
  changed: true,
};

describe("HistoryPanel", () => {
  it("shows requests as text, with details and 'use again'", async () => {
    installFetch({
      "GET /api/history?limit=50": () => fake(200, { items: [item], next_before: null }),
      "GET /api/history/7": () =>
        fake(200, { ...item, summary: "FULL SUMMARY TEXT", plan_id: "p", journal: "j.jsonl" }),
    });
    const reuse = vi.fn();
    render(<HistoryPanel onReuse={reuse} onClose={() => {}} />);
    await screen.findByText(EVIL);
    expect(document.querySelector("img")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    await screen.findByText(/FULL SUMMARY TEXT/);
    fireEvent.click(screen.getByRole("button", { name: /use again/i }));
    expect(reuse).toHaveBeenCalledWith(EVIL);
  });

  it("asks before clearing, and sends the confirmation only after Yes", async () => {
    const calls = installFetch({
      "GET /api/history?limit=50": () => fake(200, { items: [item], next_before: null }),
      "POST /api/history/clear": () => fake(200, { deleted: 1 }),
    });
    render(<HistoryPanel onReuse={() => {}} onClose={() => {}} />);
    await screen.findByText(EVIL);
    fireEvent.click(screen.getByRole("button", { name: /clear history/i }));
    expect(calls.some((c) => c.url === "/api/history/clear")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /yes, clear/i }));
    await screen.findByText(/nothing here yet/i);
    const sent = calls.find((c) => c.url === "/api/history/clear");
    expect(sent.body).toEqual({ confirm: true });
  });
});

describe("SettingsPanel", () => {
  it("sends a real boolean when a setting is toggled", async () => {
    const row = (value) => ({
      key: "history_enabled",
      label: "Save request history",
      description: "Keeps a list.",
      type: "bool",
      value,
    });
    const calls = installFetch({
      "GET /api/settings": () => fake(200, { settings: [row(true)] }),
      "POST /api/settings": () => fake(200, { settings: [row(false)] }),
    });
    render(<SettingsPanel onClose={() => {}} />);
    const box = await screen.findByRole("checkbox", { name: /save request history/i });
    expect(box.checked).toBe(true);
    fireEvent.click(box);
    await waitFor(() => expect(screen.getByRole("checkbox").checked).toBe(false));
    expect(calls.find((c) => c.method === "POST").body).toEqual({
      key: "history_enabled",
      value: false,
    });
  });
});