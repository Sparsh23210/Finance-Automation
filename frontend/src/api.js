// api.js - All backend calls in one place.
const BASE = "http://localhost:8000";

async function request(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json();
}

export const api = {
  submitTask: (req, workflow = "invoice") =>
    request("POST", "/tasks", { request: req, workflow }),
  listTasks: () => request("GET", "/tasks"),
  getTask: (id) => request("GET", `/tasks/${id}`),
  getEvidence: (id) => request("GET", `/tasks/${id}/evidence`),
  getApproval: (id) => request("GET", `/tasks/${id}/approval`),
  decideApproval: (id, decision, decided_by) =>
    request("POST", `/tasks/${id}/approval/decide`, { decision, decided_by }),
  listInvoices: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request("GET", `/finance/invoices${q ? `?${q}` : ""}`);
  },
  listVendors: (name) =>
    request("GET", `/finance/vendors${name ? `?name=${encodeURIComponent(name)}` : ""}`),
  listPOs: () => request("GET", "/finance/purchase-orders"),
  health: () => request("GET", "/health"),
};
