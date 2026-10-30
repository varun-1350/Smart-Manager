// Turns the visible conversation into plain text you can paste anywhere.
export function buildTranscript(items) {
  const blocks = [];
  for (const item of items) {
    if (item.role === "user") {
      blocks.push(`> ${item.text}`);
    } else if (item.kind === "approval") {
      blocks.push(`[approval ${item.state}]\n${item.turn.message}`);
    } else if (item.kind === "result") {
      blocks.push(item.turn.message);
    } else if (item.kind === "undo") {
      const lines = item.outcomes.map((o) => `  [${o.status}] ${o.message}`);
      blocks.push(["Undo:", ...lines].join("\n"));
    } else {
      blocks.push(`[${item.kind}] ${item.text}`);
    }
  }
  return blocks.join("\n\n");
}