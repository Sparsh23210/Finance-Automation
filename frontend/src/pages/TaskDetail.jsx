import { useState, useEffect } from "react";
import { api } from "../api";
import { StatusBadge, timeAgo } from "../components/Badges";

export default function TaskDetail({ taskId }) {
  const [task, setTask] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [approval, setApproval] = useState(null);
  const [approver, setApprover] = useState("admin");
  const [deciding, setDeciding] = useState(false);

  useEffect(() => {
    if (!taskId) return;
    fetchAll();
    // Poll every 2s while task is running
    const id = setInterval(() => {
      fetchAll();
    }, 2000);
    return () => clearInterval(id);
  }, [taskId]);

  async function fetchAll() {
    try {
      const t = await api.getTask(taskId);
      setTask(t);
      const ev = await api.getEvidence(taskId);
      setEvidence(ev);
      if (t.status === "waiting_approval") {
        try { setApproval(await api.getApproval(taskId)); } catch {
          // ignore error if approval record not yet generated
        }
      }
      // Stop polling when terminal
      if (["completed", "failed", "needs_input"].includes(t.status)) return;
    } catch {
      // ignore network errors during background polling
    }
  }

  async function handleDecision(decision) {
    setDeciding(true);
    try {
      await api.decideApproval(taskId, decision, approver);
      fetchAll();
    } catch (e) {
      alert(e.message);
    } finally {
      setDeciding(false);
    }
  }

  if (!taskId) return (
    <div className="empty-state">
      <div className="empty-state-icon">🔍</div>
      <div className="empty-state-text">Select or submit a task to see details</div>
    </div>
  );

  if (!task) return <div style={{ padding: 24, color: "var(--text-muted)" }}>Loading…</div>;

  const steps = task.state_json?.steps || [];
  const verification = task.state_json?.verification || {};
  const summary = task.state_json?.summary || task.status;
  const errors = task.state_json?.errors || [];
  const invoiceId = task.state_json?.invoice_id;
  const extracted = task.state_json?.extracted || {};

  return (
    <div>
      {/* Header */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6 }}>
              {task.workflow} · {task.id.slice(0, 8)} · {timeAgo(task.created_at)}
            </div>
            <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 10 }}>{task.request}</div>
          </div>
          <StatusBadge status={task.status} />
        </div>

        {summary && (
          <div style={{
            background: "var(--bg-elevated)", borderRadius: 8, padding: "10px 14px",
            fontSize: 13, color: "var(--text-secondary)", borderLeft: "3px solid var(--accent)"
          }}>
            {summary}
          </div>
        )}

        {errors.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {errors.slice(-3).map((e, i) => (
              <div key={i} style={{ color: "var(--red)", fontSize: 12, padding: "4px 0" }}>⚠ {e}</div>
            ))}
          </div>
        )}
      </div>

      {/* Approval panel */}
      {task.status === "waiting_approval" && approval && (
        <div className="card" style={{ borderColor: "var(--yellow)" }}>
          <div className="card-title" style={{ color: "var(--yellow)" }}>⚠ Approval Required</div>
          <div style={{ marginBottom: 12 }}>
            <strong>{approval.action}</strong><br />
            <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              {approval.justification}
            </span>
          </div>
          {approval.evidence_summary && (
            <pre className="code-block">{JSON.stringify(approval.evidence_summary, null, 2)}</pre>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 14, alignItems: "center" }}>
            <input
              style={{ width: 160 }}
              placeholder="Approver name"
              value={approver}
              onChange={e => setApprover(e.target.value)}
            />
            <button className="btn btn-success" onClick={() => handleDecision("approved")} disabled={deciding}>
              ✓ Approve
            </button>
            <button className="btn btn-danger" onClick={() => handleDecision("rejected")} disabled={deciding}>
              ✗ Reject
            </button>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
            Authorized approvers: admin, finance_manager, dev
          </div>
        </div>
      )}

      {/* Execution Timeline */}
      {steps.length > 0 && (
        <div className="card">
          <div className="card-title">Execution Timeline</div>
          <div className="timeline">
            {steps.map((step, i) => (
              <div className="timeline-item" key={i}>
                <div className={`timeline-dot ${step.status}`} />
                <div className="timeline-content">
                  <div className="timeline-header">
                    <span className="timeline-tool">{step.tool}</span>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <span style={{
                        fontSize: 11, padding: "2px 8px", borderRadius: 12,
                        background: step.status === "ok" ? "rgba(34,197,94,0.1)" :
                          step.status === "error" ? "rgba(239,68,68,0.1)" : "rgba(245,158,11,0.1)",
                        color: step.status === "ok" ? "var(--green)" :
                          step.status === "error" ? "var(--red)" : "var(--yellow)"
                      }}>
                        {step.status}
                      </span>
                      <span className="timeline-step">step {i + 1}</span>
                      {step.attempt > 0 && (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          attempt {step.attempt + 1}
                        </span>
                      )}
                    </div>
                  </div>
                  {step.args && Object.keys(step.args).length > 0 && (
                    <pre className="code-block">{JSON.stringify(step.args, null, 2)}</pre>
                  )}
                  {step.result?.error && (
                    <div style={{ color: "var(--red)", fontSize: 12, marginTop: 6 }}>
                      ✗ {step.result.error}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extracted Fields */}
      {Object.keys(extracted).length > 0 && (
        <div className="card">
          <div className="card-title">Extracted Invoice Fields</div>
          <div className="check-grid">
            {Object.entries(extracted).map(([k, v]) => (
              <div className="check-item" key={k}>
                <div className="check-label">{k.replace(/_/g, " ")}</div>
                <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>
                  {v ?? <span style={{ color: "var(--text-muted)" }}>null</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Verification */}
      {Object.keys(verification).length > 0 && (
        <div className="card">
          <div className="card-title">Independent Verification</div>
          <div style={{ marginBottom: 10, fontSize: 12, color: "var(--text-muted)" }}>
            These checks read the database record independently — not based on what the agent said.
            {invoiceId && ` · Invoice DB ID: ${invoiceId}`}
          </div>
          <div className="check-grid">
            {Object.entries(verification).map(([field, result]) => {
              const isPass = result === "PASS";
              const isNC = !result || result === "NOT_CHECKED";
              return (
                <div className="check-item" key={field}
                  style={{ borderColor: isPass ? "rgba(34,197,94,0.3)" : isNC ? "" : "rgba(239,68,68,0.3)" }}>
                  <div className="check-label">{field.replace(/_/g, " ")}</div>
                  <div className={`check-value ${isPass ? "check-pass" : isNC ? "check-nc" : "check-fail"}`}>
                    {isPass ? "✓ PASS" : isNC ? "— NOT CHECKED" : `✗ ${result}`}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Evidence Ledger */}
      {evidence.length > 0 && (
        <div className="card">
          <div className="card-title">Evidence Ledger ({evidence.length} entries)</div>
          <table className="evidence-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Action</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Source</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {evidence.map(ev => (
                <tr key={ev.id}>
                  <td style={{ color: "var(--text-muted)", fontFamily: "monospace" }}>{ev.step}</td>
                  <td>{ev.action}</td>
                  <td style={{ color: "var(--accent-light)", fontFamily: "monospace", fontSize: 12 }}>
                    {ev.tool_name || "—"}
                  </td>
                  <td>
                    <span style={{
                      color: ev.status === "ok" ? "var(--green)" :
                        ev.status === "error" || ev.status === "fail" ? "var(--red)" : "var(--yellow)"
                    }}>
                      {ev.status}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{ev.source_ref || "—"}</td>
                  <td style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
