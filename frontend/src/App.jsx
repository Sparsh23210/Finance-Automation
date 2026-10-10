import { useState, useEffect } from "react";
import { api } from "./api";
import TaskSubmit from "./pages/TaskSubmit";
import TaskDetail from "./pages/TaskDetail";
import FinanceView from "./pages/FinanceView";

const NAV = [
  { id: "submit",  icon: "⚡", label: "Submit Task" },
  { id: "detail",  icon: "🔍", label: "Task Detail" },
  { id: "finance", icon: "📊", label: "Finance Data" },
];

export default function App() {
  const [page, setPage] = useState("submit");
  const [selectedTask, setSelectedTask] = useState(null);
  const [backendOk, setBackendOk] = useState(null);

  useEffect(() => {
    api.health()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  function handleTaskCreated(taskId) {
    setSelectedTask(taskId);
    setPage("detail");
  }

  const pageTitle = {
    submit:  { title: "Submit Task", sub: "Describe a business task for the agent to execute autonomously" },
    detail:  { title: "Task Detail", sub: selectedTask ? `Task ${selectedTask.slice(0, 8)}` : "Select a task" },
    finance: { title: "Finance Data", sub: "Live view of invoices, vendors, and purchase orders" },
  }[page];

  return (
    <div className="app">
      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">🔁</div>
          <div>
            <div className="logo-text">ProofLoop</div>
            <div className="logo-sub">AI Task Worker</div>
          </div>
        </div>

        {NAV.map(n => (
          <div
            key={n.id}
            className={`nav-item ${page === n.id ? "active" : ""}`}
            onClick={() => setPage(n.id)}
          >
            <span className="nav-icon">{n.icon}</span>
            {n.label}
          </div>
        ))}

        {/* Backend status indicator */}
        <div style={{ marginTop: "auto", padding: "8px 10px", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Backend</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%", display: "inline-block",
              background: backendOk === null ? "var(--text-muted)" :
                backendOk ? "var(--green)" : "var(--red)"
            }} />
            {backendOk === null ? "checking…" : backendOk ? "connected" : "offline"}
          </div>
        </div>
      </nav>

      {/* Main area */}
      <div className="main">
        <div className="topbar">
          <div>
            <div className="page-title">{pageTitle?.title}</div>
            <div className="page-sub">{pageTitle?.sub}</div>
          </div>
          {backendOk === false && (
            <div style={{
              background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)",
              color: "var(--red)", padding: "6px 14px", borderRadius: 8, fontSize: 12
            }}>
              ⚠ Backend offline — start the FastAPI server on port 8000
            </div>
          )}
        </div>

        <div className="content">
          {page === "submit"  && <TaskSubmit onTaskCreated={handleTaskCreated} />}
          {page === "detail"  && <TaskDetail taskId={selectedTask} />}
          {page === "finance" && <FinanceView />}
        </div>
      </div>
    </div>
  );
}
