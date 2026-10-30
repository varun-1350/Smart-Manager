let token = null;

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function setToken(value) {
  token = value;
}

// Inside the desktop window the shell hands us the token. In a normal browser (development)
// there is no shell, so we return null and the page asks you to paste it.
export async function getToken(attempts = 40) {
  for (let i = 0; i < attempts; i++) {
    const bridge = window.pywebview && window.pywebview.api;
    if (bridge && typeof bridge.get_token === "function") return bridge.get_token();
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return null;
}

function explain(status, data) {
  if (status === 401) return "The session token is missing or wrong.";
  if (status === 409) return "Another request is still running. Please wait a moment.";
  if (status === 422) return "That request wasn't accepted (it may be too long).";
  if (data && typeof data.detail === "string") return data.detail;
  return `The request failed (${status}).`;
}

async function call(path, method = "GET", body) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-Session-Token": token || "" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "I can't reach the local server. Is it still running?");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* no body */
  }
  if (!res.ok) throw new ApiError(res.status, explain(res.status, data));
  return data;
}

export const sendMessage = (text) => call("/message", "POST", { text });
export const approve = (turn_id, digest) => call("/approve", "POST", { turn_id, digest });
export const reject = (turn_id) => call("/reject", "POST", { turn_id });
export const cancel = () => call("/cancel", "POST", {});
export const getUndoPreview = () => call("/undo");
export const undo = () => call("/undo", "POST", { confirm: true });
export const getInterrupted = () => call("/interrupted");
export const dismissRun = (run_id) => call("/interrupted/dismiss", "POST", { run_id });
export const undoRun = (run_id) =>
  call("/interrupted/undo", "POST", { run_id, confirm: true });

export const getHistory = (before) =>
  call(`/history?limit=50${before ? `&before_id=${before}` : ""}`);
export const getHistoryItem = (id) => call(`/history/${id}`);
export const clearHistory = () => call("/history/clear", "POST", { confirm: true });
export const getSettings = () => call("/settings");
export const setSetting = (key, value) => call("/settings", "POST", { key, value });
export const getProgress = () => call("/progress");