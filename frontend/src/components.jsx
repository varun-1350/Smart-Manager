// Everything here renders server text as TEXT. File names are untrusted input, so there is
// no dangerouslySetInnerHTML anywhere in this app.
import { useState } from "react";
export function Pre({ text }) {
  return <pre className="pre">{text}</pre>;
}

const RISK_LABEL = { low: "Low", medium: "Medium", high: "High", destructive: "Delete" };
const SHOW_FIRST = 30;
const STATUS_TEXT = {
  pending: "waiting",
  running: "working…",
  success: "done",
  failed: "failed",
  cancelled: "skipped",
};

export function ApprovalCard({ item, busy, onApprove, onReject }) {
  const { turn, state } = item; // waiting | working | approved | rejected | stopped
  const preview = turn.preview;
  const [showAll, setShowAll] = useState(false);
  const ops = preview ? preview.operations : [];
  const shown = showAll ? ops : ops.slice(0, SHOW_FIRST);
  const hasDelete = ops.some((o) => o.risk === "destructive");
  const label =
    ops.length > 0 ? `Approve ${ops.length} change${ops.length === 1 ? "" : "s"}` : "Approve";
  return (
    <div className="card approval">
      <div className="card-title">Please review. Nothing has been changed yet.</div>
      {!preview && <Pre text={turn.message} />}
      {preview &&
        preview.reads.map((r) => (
          <div key={r.task_id} className="muted">
            Found {r.count} item{r.count === 1 ? "" : "s"} in {r.scope}
            {r.truncated ? " (stopped early: too many matches)" : ""}
          </div>
        ))}
      {preview && (
        <ul className="ops">
          {shown.map((o, i) => (
            <li key={i} className="op">
              <span className={`risk ${o.risk}`}>{RISK_LABEL[o.risk] || o.risk}</span>
              {o.description}
              {o.warnings.map((w, j) => (
                <div key={j} className="note">
                  {w}
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
      {ops.length > SHOW_FIRST && !showAll && (
        <button onClick={() => setShowAll(true)}>Show all {ops.length}</button>
      )}
      {hasDelete && (
        <div className="muted">
          Deleted items go to the Recycle Bin, so you can restore them there.
        </div>
      )}
      {state === "waiting" && (
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => onApprove(item)}>
            {label}
          </button>
          <button disabled={busy} onClick={() => onReject(item)}>
            Reject
          </button>
        </div>
      )}
      {state === "working" && <div className="muted">Working…</div>}
      {state === "approved" && <div className="muted">Approved.</div>}
      {state === "rejected" && <div className="muted">Rejected. Nothing was changed.</div>}
      {state === "stopped" && <div className="muted">This request was not run.</div>}
    </div>
  );
}

export function ProgressCard({ progress }) {
  return (
    <div className="card" role="status">
      <div className="card-title">Working…</div>
      <ul className="steps">
        {progress.tasks.map((t) => (
          <li key={t.task_id} className={`step ${t.status}`}>
            {t.label}: {STATUS_TEXT[t.status] || t.status}
          </li>
        ))}
      </ul>
    </div>
  );
}
export function ResultCard({ turn }) {
  const r = turn.report;
  const cls = r.succeeded ? "ok" : r.status === "cancelled" ? "warn" : "bad";
  const label = r.succeeded ? "Done" : r.status === "cancelled" ? "Cancelled" : "Did not finish";
  return (
    <div className="card">
      <div className={`badge ${cls}`}>
        {label}
        {r.partial ? " (some changes were made)" : ""}
      </div>
      <Pre text={turn.message} />
      {r.warnings.map((w, i) => (
        <div key={i} className="note">
          {w}
        </div>
      ))}
    </div>
  );
}

export function UndoResult({ outcomes }) {
  return (
    <div className="card">
      <div className="card-title">Undo</div>
      <ul>
        {outcomes.map((o, i) => (
          <li key={i}>
            <strong>{o.status}</strong>: {o.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function UndoDialog({ title, steps, busy, onConfirm, onCancel }) {
  return (
    <div className="card undo">
      <div className="card-title">{title}</div>
      {steps.length === 0 ? (
        <div className="muted">Nothing to undo.</div>
      ) : (
        <ul>
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
      <div className="row">
        {steps.length > 0 && (
          <button className="primary" disabled={busy} onClick={onConfirm}>
            Yes, undo these
          </button>
        )}
        <button disabled={busy} onClick={onCancel}>
          Close
        </button>
      </div>
    </div>
  );
}

export function RecoveryPanel({ reports, errors, busy, onUndo, onDismiss }) {
  if (!reports.length && !errors.length) return null;
  return (
    <div className="banner warn">
      <strong>An earlier run didn't finish.</strong>
      {errors.map((e, i) => (
        <div key={i} className="note">
          Couldn't read a journal file: {e}
        </div>
      ))}
      {reports.map((r) => (
        <div key={r.run_id} className="run">
          {r.damaged && (
            <div className="note">This record is partly damaged, so it may be incomplete.</div>
          )}
          <ul>
            {r.unknown.map((s) => (
              <li key={s.index}>
                {s.description}{" "}
                <span className="muted">
                  ({s.state.replace("_", " ")}) {s.note}
                </span>
              </li>
            ))}
          </ul>
          <div className="row">
            {r.undo_preview.length > 0 && (
              <button disabled={busy} onClick={() => onUndo(r)}>
                Undo what was done…
              </button>
            )}
            <button disabled={busy} onClick={() => onDismiss(r)}>
              I've checked, dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}