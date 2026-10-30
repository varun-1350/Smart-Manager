import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApprovalCard, ProgressCard } from "./components.jsx";

afterEach(cleanup);

const op = (i, risk = "high", extra = {}) => ({
  task_id: "t1",
  action: "move_file",
  description: `Move file${i}.pdf -> Archive`,
  risk,
  warnings: [],
  ...extra,
});

const item = (ops) => ({
  id: 1,
  state: "waiting",
  turn: {
    turn_id: "x",
    digest: "d".repeat(64),
    message: "fallback text",
    preview: {
      reads: [{ task_id: "t1", count: 3, scope: "D:\\Work", truncated: false, sample: [] }],
      operations: ops,
      needs_approval: true,
    },
  },
});

describe("ApprovalCard", () => {
  it("lists each change with its risk and counts them on the button", () => {
    render(
      <ApprovalCard
        item={item([op(1), op(2, "destructive")])}
        busy={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Approve 2 changes" })).toBeTruthy();
    expect(screen.getByText("Delete")).toBeTruthy();
    expect(screen.getByText(/Recycle Bin/)).toBeTruthy();
    expect(screen.getByText(/Found 3 items in D:\\Work/)).toBeTruthy();
  });

  it("collapses long lists until asked", () => {
    const many = Array.from({ length: 35 }, (_, i) => op(i));
    render(<ApprovalCard item={item(many)} busy={false} onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(document.querySelectorAll(".op").length).toBe(30);
    fireEvent.click(screen.getByRole("button", { name: "Show all 35" }));
    expect(document.querySelectorAll(".op").length).toBe(35);
  });

  it("shows paths as text and never as HTML", () => {
    const evil = '<img src=x onerror="alert(1)">.pdf';
    render(
      <ApprovalCard
        item={item([op(1, "high", { description: `Move ${evil} -> Archive` })])}
        busy={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(new RegExp("onerror"))).toBeTruthy();
  });

  it("falls back to the plain text when there is no structured preview", () => {
    const plain = { id: 1, state: "waiting", turn: { turn_id: "x", digest: "d", message: "fallback text" } };
    render(<ApprovalCard item={plain} busy={false} onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText("fallback text")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("approves the item it was given", () => {
    const onApprove = vi.fn();
    const it1 = item([op(1)]);
    render(<ApprovalCard item={it1} busy={false} onApprove={onApprove} onReject={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onApprove).toHaveBeenCalledWith(it1);
  });
});

describe("ProgressCard", () => {
  it("shows each step and where it is", () => {
    render(
      <ProgressCard
        progress={{
          running: true,
          tasks: [
            { task_id: "t1", label: "Search", status: "success" },
            { task_id: "t2", label: "Move (3 items)", status: "running" },
            { task_id: "t3", label: "Open", status: "pending" },
          ],
        }}
      />
    );
    expect(screen.getByText("Search: done")).toBeTruthy();
    expect(screen.getByText("Move (3 items): working…")).toBeTruthy();
    expect(screen.getByText("Open: waiting")).toBeTruthy();
  });
});