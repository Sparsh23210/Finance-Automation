import { useState, useEffect, useCallback } from "react";
import { api } from "../api";
import { StatusBadge, Spinner } from "../components/Badges";

const EXAMPLE_TASKS = [
  {
    text: "Find the latest invoice from Apex Supplies, extract the amount and due date, enter it into the finance application, and flag it if the amount exceeds INR 50,000.",
    workflow: "invoice",
  },
  {
    text: "Find the latest invoice from Global Tech Solutions, locate its matching purchase order, compare the relevant fields, and flag discrepancies.",
    workflow: "po_reconciliation",
  },
  {
    text: "Search for the invoice INV-RAPID-2024-007 from Rapid Logistics, extract all fields, and create it in the system.",
    workflow: "invoice",
  },
];

export default function TaskSubmit({ onTaskCreated }) {
  const [request, setRequest] = useState("");
  const [workflow, setWorkflow] = useState("invoice");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [recentTasks, setRecentTasks] = useState([]);

  const fetchTasks = useCallback(async () => {
    try {
      const tasks = await api.listTasks();
      setRecentTasks(tasks.slice(0, 5));
    } catch {
      // ignore network errors during background polling
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const id = setInterval(fetchTasks, 3000);
    return () => clearInterval(id);
  }, [fetchTasks]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!request.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const task = await api.submitTask(request.trim(), workflow);
      setRequest("");
      fetchTasks();
      if (onTaskCreated) onTaskCreated(task.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-value stat-blue">{recentTasks.length}</div>
          <div className="stat-label">Recent Tasks</div>
        </div>
        <div className="stat-card">
          <div className="stat-value stat-green">
            {recentTasks.filter(t => t.status === "completed").length}
          </div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value stat-red">
            {recentTasks.filter(t => t.status === "failed").length}
          </div>
          <div className="stat-label">Failed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: "var(--yellow)" }}>
            {recentTasks.filter(t => t.status === "waiting_approval").length}
          </div>
          <div className="stat-label">Awaiting Approval</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Submit New Task</div>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label>Workflow Type</label>
            <select value={workflow} onChange={e => setWorkflow(e.target.value)}>
              <option value="invoice">Invoice Entry</option>
              <option value="po_reconciliation">PO Reconciliation</option>
            </select>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label>Natural-Language Task</label>
            <textarea
              value={request}
              onChange={e => {
                const val = e.target.value;
                setRequest(val);
                const low = val.toLowerCase();
                if (low.includes("purchase order") || low.includes("matching po") || low.includes("reconcil") || low.includes("discrepanc")) {
                  setWorkflow("po_reconciliation");
                }
              }}
              placeholder="Describe what you want the agent to do…"
              rows={4}
            />
          </div>
          {error && (
            <div style={{ color: "var(--red)", marginBottom: 10, fontSize: 13 }}>
              ✗ {error}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={loading || !request.trim()}>
            {loading ? <><Spinner /> Submitting…</> : "▶ Run Agent"}
          </button>
        </form>

        <div style={{ marginTop: 18 }}>
          <div className="card-title">Example Tasks</div>
          <div className="suggestions">
            {EXAMPLE_TASKS.map((t, i) => (
              <span
                key={i}
                className="chip"
                onClick={() => {
                  setRequest(t.text);
                  setWorkflow(t.workflow);
                }}
              >
                {t.text.slice(0, 60)}…
              </span>
            ))}
          </div>
        </div>
      </div>

      {recentTasks.length > 0 && (
        <div className="card">
          <div className="card-title">Recent Tasks</div>
          {recentTasks.map(task => (
            <div
              key={task.id}
              onClick={() => onTaskCreated && onTaskCreated(task.id)}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "10px 12px", borderRadius: 8, cursor: "pointer",
                marginBottom: 6, background: "var(--bg-elevated)",
                transition: "background 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
              onMouseLeave={e => e.currentTarget.style.background = "var(--bg-elevated)"}
            >
              <div>
                <div style={{ fontSize: 13, marginBottom: 3 }}>
                  {task.request.slice(0, 70)}{task.request.length > 70 ? "…" : ""}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  {task.workflow} · {task.id.slice(0, 8)}
                </div>
              </div>
              <StatusBadge status={task.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
