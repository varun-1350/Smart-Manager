import { useCallback, useEffect, useState } from "react";
import * as api from "./api.js";
import { Pre } from "./components.jsx";

// Everything from the server is rendered as text, never as HTML.
const when = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
};

export function HistoryPanel({ onReuse, onClose }) {
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async (before) => {
    setLoading(true);
    setError("");
    try {
      const data = await api.getHistory(before);
      setItems((prev) => (before ? [...prev, ...data.items] : data.items));
      setNext(data.next_before);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(null);
  }, [load]);

  const toggleDetail = async (item) => {
    if (detail && detail.id === item.id) {
      setDetail(null);
      return;
    }
    try {
      setDetail(await api.getHistoryItem(item.id));
    } catch (e) {
      setError(e.message);
    }
  };

  const clear = async () => {
    try {
      await api.clearHistory();
      setItems([]);
      setNext(null);
      setDetail(null);
    } catch (e) {
      setError(e.message);
    }
    setConfirming(false);
  };

  return (
    <section className="panel" aria-label="History">
      <div className="panel-head">
        <strong>History</strong>
        <button onClick={onClose}>Close</button>
      </div>
      <p className="muted">
        Saved on this computer only. It includes your requests and the file paths in them.
      </p>
      {error && <div className="note">{error}</div>}
      {!loading && !error && items.length === 0 && <p className="muted">Nothing here yet.</p>}
      {items.map((item) => (
        <div key={item.id} className="hist-item">
          <div className="hist-req">{item.request}</div>
          <div className="muted">
            {when(item.created_at)} · {item.status}
            {item.changed ? " · changed files" : ""}
          </div>
          <div className="row">
            <button onClick={() => toggleDetail(item)}>
              {detail && detail.id === item.id ? "Hide details" : "Details"}
            </button>
            <button onClick={() => onReuse(item.request)}>Use again</button>
          </div>
          {detail && detail.id === item.id && <Pre text={detail.summary} />}
        </div>
      ))}
      {loading && <p className="muted">Loading…</p>}
      {next && !loading && <button onClick={() => load(next)}>Load more</button>}
      {items.length > 0 && !confirming && (
        <div className="row">
          <button onClick={() => setConfirming(true)}>Clear history…</button>
        </div>
      )}
      {confirming && (
        <div className="note">
          Delete all saved history? This can't be undone.
          <div className="row">
            <button className="primary" onClick={clear}>
              Yes, clear
            </button>
            <button onClick={() => setConfirming(false)}>No</button>
          </div>
        </div>
      )}
    </section>
  );
}

export function SettingsPanel({ onClose }) {
  const [settings, setSettings] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSettings()
      .then((d) => setSettings(d.settings))
      .catch((e) => setError(e.message));
  }, []);

  const toggle = async (s) => {
    setError("");
    try {
      const data = await api.setSetting(s.key, !s.value); // always a real true/false
      setSettings(data.settings);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <section className="panel" aria-label="Settings">
      <div className="panel-head">
        <strong>Settings</strong>
        <button onClick={onClose}>Close</button>
      </div>
      {error && <div className="note">{error}</div>}
      {settings.map((s) => (
        <div key={s.key} className="setting">
          <label>
            <input type="checkbox" checked={s.value} onChange={() => toggle(s)} /> {s.label}
          </label>
          <div className="muted">{s.description}</div>
        </div>
      ))}
      <div className="setting">
        <strong>Optional language model</strong>
        <div className="muted">
          Not installed. Everything works without it, and Smart Manager itself never uses the
          internet.
        </div>
      </div>
      <p className="muted">
        Your data lives in the app's data folder: the history database, the safety journal, and
        backups of edited files.
      </p>
    </section>
  );
}