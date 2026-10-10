// Badge component for task status and verification checks
export function StatusBadge({ status }) {
  const map = {
    running: "badge-running",
    completed: "badge-completed",
    failed: "badge-failed",
    waiting_approval: "badge-waiting",
    needs_input: "badge-needs_input",
  };
  const cls = map[status] || "badge-not_checked";
  const dot = status === "running" ? "● " : "";
  return (
    <span className={`badge ${cls} ${status === "running" ? "pulse" : ""}`}>
      {dot}{status?.replace("_", " ")}
    </span>
  );
}

export function CheckBadge({ value }) {
  if (!value || value === "NOT_CHECKED") return <span className="badge badge-not_checked">—</span>;
  if (value === "PASS") return <span className="badge badge-pass">✓ PASS</span>;
  return <span className="badge badge-fail">✗ FAIL</span>;
}

export function Spinner() {
  return <span className="spinner" />;
}

// Relative time formatter
export function timeAgo(iso) {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}
