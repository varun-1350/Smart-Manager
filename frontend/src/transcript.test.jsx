import { describe, expect, it } from "vitest";
import { buildTranscript } from "./transcript.js";

describe("buildTranscript", () => {
  it("includes requests, previews, results, refusals and undo", () => {
    const text = buildTranscript([
      { role: "user", text: "delete a.pdf" },
      { role: "assistant", kind: "approval", state: "waiting", turn: { message: "Planned changes (1)" } },
      { role: "assistant", kind: "result", turn: { message: "Result: completed" } },
      { role: "assistant", kind: "blocked", text: "I can't do that" },
      { role: "assistant", kind: "undo", outcomes: [{ status: "undone", message: "Moved back" }] },
    ]);
    expect(text).toContain("> delete a.pdf");
    expect(text).toContain("[approval waiting]\nPlanned changes (1)");
    expect(text).toContain("Result: completed");
    expect(text).toContain("[blocked] I can't do that");
    expect(text).toContain("[undone] Moved back");
  });

  it("is empty for an empty chat", () => {
    expect(buildTranscript([])).toBe("");
  });
});