import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api.js";
import { copyText } from "./clipboard.js";
import {
  ApprovalCard,
  ProgressCard,
  RecoveryPanel,
  ResultCard,
  UndoDialog,
  UndoResult,
} from "./components.jsx";
import { HistoryPanel, SettingsPanel } from "./panels.jsx";
import { buildTranscript } from "./transcript.js";

let nextId = 1;
const newId = () => nextId++;

const EXAMPLES = ["list files", "find PDFs", "create a folder named Test", "copy the path of notes.txt"];
const MAX_RECALL = 50;

export default function App() {
  const [phase, setPhase] = useState("starting"); // starting | needs-token | ready
  const [tokenInput, setTokenInput] = useState("");
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [undoAvailable, setUndoAvailable] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [panel, setPanel] = useState(null); // null | "history" | "settings"
  const [progress, setProgress] = useState(null);
  const [chatCopy, setChatCopy] = useState("");
  const [recovery, setRecovery] = useState({ reports: [], errors: [] });
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const startedRef = useRef(false);
  const recallRef = useRef({ list: [], pos: -1 });

  const add = useCallback(
    (item) => setItems((prev) => [...prev, { id: newId(), ...item }]),
    []
  );
  const patch = useCallback(
    (id, change) =>
      setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...change } : i))),
    []
  );

  // Runs one API action with the busy flag and error reporting. Returns null on failure.
  const run = useCallback(
    async (fn) => {
      setBusy(true);
      try {
        return await fn();
      } catch (e) {
        add({ role: "assistant", kind: "error", text: e.message || "Something went wrong." });
        return null;
      } finally {
        setBusy(false);
      }
    },
    [add]
  );

  const refreshUndo = useCallback(async () => {
    try {
      const data = await api.getUndoPreview();
      setUndoAvailable(data.steps.length > 0);
    } catch {
      /* undo is a convenience; failing to check isn't worth an error message */
    }
  }, []);

  const loadRecovery = useCallback(async () => {
    try {
      const data = await api.getInterrupted();
      setRecovery({ reports: data.reports, errors: data.errors });
    } catch (e) {
      add({ role: "assistant", kind: "error", text: e.message });
    }
  }, [add]);

  // 1. get the session token (from the desktop shell, or ask for it in a browser)
  useEffect(() => {
    let alive = true;
    api.getToken().then((t) => {
      if (!alive) return;
      if (t) {
        api.setToken(t);
        setPhase("ready");
      } else {
        setPhase("needs-token");
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  // 2. once connected, check for an interrupted run and for undo (one at a time:
  //    the server answers 409 if two requests overlap)
  useEffect(() => {
    if (phase !== "ready" || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      setBusy(true);
      await loadRecovery();
      await refreshUndo();
      setBusy(false);
    })();
  }, [phase, loadRecovery, refreshUndo]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [items, dialog, progress]);

  // Put the cursor back in the box whenever a request finishes.
  useEffect(() => {
    if (phase === "ready" && !busy && !panel) inputRef.current?.focus?.();
  }, [phase, busy, panel]);

  // While a request runs, ask the server what it is doing. This endpoint is never blocked.
  useEffect(() => {
    if (!busy) {
      setProgress(null);
      return undefined;
    }
    const timer = setInterval(async () => {
      try {
        const p = await api.getProgress();
        setProgress(p.running && p.tasks.length ? p : null);
      } catch {
        /* progress is only a nicety */
      }
    }, 500);
    return () => clearInterval(timer);
  }, [busy]);

  const showTurn = useCallback(
    (turn) => {
      if (turn.kind === "needs_approval") {
        add({ role: "assistant", kind: "approval", turn, state: "waiting" });
      } else if (turn.kind === "executed") {
        add({ role: "assistant", kind: "result", turn });
      } else {
        add({ role: "assistant", kind: turn.kind, text: turn.message });
      }
    },
    [add]
  );

  const submit = async (e) => {
    e.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setText("");
    const recall = recallRef.current;
    if (recall.list[recall.list.length - 1] !== value) {
      recall.list.push(value);
      if (recall.list.length > MAX_RECALL) recall.list.shift();
    }
    recall.pos = -1;
    add({ role: "user", text: value });
    const turn = await run(() => api.sendMessage(value));
    if (turn) {
      showTurn(turn);
      if (turn.kind === "executed") await refreshUndo();
    }
  };

  // Up/Down walk through earlier requests, like a terminal.
  const onKeyDown = (e) => {
    const recall = recallRef.current;
    if (e.key === "ArrowUp" && recall.list.length) {
      e.preventDefault();
      recall.pos = recall.pos < 0 ? recall.list.length - 1 : Math.max(0, recall.pos - 1);
      setText(recall.list[recall.pos]);
    } else if (e.key === "ArrowDown" && recall.pos >= 0) {
      e.preventDefault();
      recall.pos += 1;
      if (recall.pos >= recall.list.length) {
        recall.pos = -1;
        setText("");
      } else {
        setText(recall.list[recall.pos]);
      }
    }
  };

  const approve = async (item) => {
    patch(item.id, { state: "working" });
    // The digest sent back is the one the server gave us for THIS preview.
    const turn = await run(() => api.approve(item.turn.turn_id, item.turn.digest));
    if (!turn) {
      patch(item.id, { state: "waiting" }); // the call failed; the preview is still valid
      return;
    }
    patch(item.id, { state: turn.kind === "executed" ? "approved" : "stopped" });
    showTurn(turn);
    if (turn.kind === "executed") await refreshUndo();
  };

  const reject = async (item) => {
    patch(item.id, { state: "rejected" });
    await run(() => api.reject(item.turn.turn_id));
  };

  const stop = () => {
    api.cancel().catch(() => {});
  };

  const openUndo = async () => {
    const data = await run(() => api.getUndoPreview());
    if (data) setDialog({ kind: "last", title: "Undo the last change?", steps: data.steps });
  };

  const confirmUndo = async () => {
    const d = dialog;
    const data = await run(() => (d.kind === "last" ? api.undo() : api.undoRun(d.runId)));
    setDialog(null);
    if (data) {
      add({ role: "assistant", kind: "undo", outcomes: data.outcomes });
      if (d.kind === "run") await loadRecovery();
      await refreshUndo();
    }
  };

  const dismissRun = async (report) => {
    await run(() => api.dismissRun(report.run_id));
    await loadRecovery();
  };

  const copyChat = async () => {
    const ok = await copyText(buildTranscript(items));
    setChatCopy(ok ? "Copied" : "Couldn't copy");
    setTimeout(() => setChatCopy(""), 1800);
  };

  const connect = (e) => {
    e.preventDefault();
    if (!tokenInput.trim()) return;
    api.setToken(tokenInput.trim());
    setPhase("ready");
  };

  if (phase === "starting") {
    return (
      <main className="shell">
        <p className="muted">Starting…</p>
      </main>
    );
  }

  if (phase === "needs-token") {
    return (
      <main className="shell">
        <form className="card" onSubmit={connect}>
          <h1>Smart Manager</h1>
          <p>Paste the session token printed by the server window.</p>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="Session token"
          />
          <button type="submit" className="primary">
            Connect
          </button>
        </form>
      </main>
    );
  }

  const waitingForYou = items.some(
    (i) => i.kind === "approval" && (i.state === "waiting" || i.state === "working")
  );

  const renderItem = (item) => {
    if (item.role === "user") {
      return (
        <div key={item.id} className="msg user">
          {item.text}
        </div>
      );
    }
    if (item.kind === "approval") {
      return (
        <ApprovalCard key={item.id} item={item} busy={busy} onApprove={approve} onReject={reject} />
      );
    }
    if (item.kind === "result") return <ResultCard key={item.id} turn={item.turn} />;
    if (item.kind === "undo") return <UndoResult key={item.id} outcomes={item.outcomes} />;
    return (
      <div key={item.id} className={`msg bot ${item.kind}`}>
        {item.text}
      </div>
    );
  };

  return (
    <main className="shell">
      <header>
        <h1>Smart Manager</h1>
        <span className="muted">Local and offline</span>
        <span className="spacer" />
        <button onClick={copyChat} disabled={items.length === 0}>
          {chatCopy || "Copy chat"}
        </button>
        <button
          onClick={() => setItems([])}
          disabled={busy || waitingForYou || items.length === 0}
          title="Clears this screen only. History and undo are not affected."
        >
          New chat
        </button>
        <button onClick={() => setPanel(panel === "history" ? null : "history")}>History</button>
        <button onClick={() => setPanel(panel === "settings" ? null : "settings")}>Settings</button>
      </header>

      <RecoveryPanel
        reports={recovery.reports}
        errors={recovery.errors}
        busy={busy}
        onUndo={(r) =>
          setDialog({
            kind: "run",
            runId: r.run_id,
            title: "Undo what the interrupted run did?",
            steps: r.undo_preview,
          })
        }
        onDismiss={dismissRun}
      />

      {panel === "history" && (
        <HistoryPanel
          onReuse={(t) => {
            setText(t);
            setPanel(null);
          }}
          onClose={() => setPanel(null)}
        />
      )}
      {panel === "settings" && <SettingsPanel onClose={() => setPanel(null)} />}

      <section className={panel ? "chat hidden" : "chat"} aria-live="polite">
        {items.length === 0 && (
          <div className="hint">
            <p className="muted">
              Try: find PDFs in Downloads, open the largest, and move the rest to Archive
            </p>
            <div className="chips">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  className="chip"
                  onClick={() => {
                    setText(example);
                    inputRef.current?.focus?.();
                  }}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {items.map(renderItem)}
        {dialog && (
          <UndoDialog
            title={dialog.title}
            steps={dialog.steps}
            busy={busy}
            onConfirm={confirmUndo}
            onCancel={() => setDialog(null)}
          />
        )}
        {progress && <ProgressCard progress={progress} />}
        <div ref={endRef} />
      </section>

      <form className={panel ? "composer hidden" : "composer"} onSubmit={submit}>
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type a request…"
          maxLength={1000}
          disabled={busy}
          autoFocus
        />
        <button type="submit" className="primary" disabled={busy || !text.trim()}>
          Send
        </button>
        {busy && (
          <button type="button" onClick={stop} title="Stops between steps, never in the middle of one">
            Stop
          </button>
        )}
        {undoAvailable && !busy && (
          <button type="button" onClick={openUndo}>
            Undo last change
          </button>
        )}
      </form>
    </main>
  );
}