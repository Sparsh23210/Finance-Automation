import { useState, useEffect } from "react";
import { api } from "../api";

function isValidInvoiceNumber(num) {
  if (!num || typeof num !== "string") return false;
  const cleaned = num.trim();
  const low = cleaned.toLowerCase();
  const disallowed = ["umber", "number", "invoice", "no", "unknown", "null", "none"];
  if (disallowed.includes(low) || cleaned.length < 3) return false;
  const hasDigit = /\d/.test(cleaned);
  const hasStructure = /[-/]/.test(cleaned);
  return hasDigit || hasStructure;
}

export default function FinanceView() {
  const [invoices, setInvoices] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [pos, setPOs] = useState([]);
  const [tab, setTab] = useState("invoices");
  const [loading, setLoading] = useState(true);
  const [vendorFilter, setVendorFilter] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [inv, vend, po] = await Promise.all([
          api.listInvoices(),
          api.listVendors(),
          api.listPOs(),
        ]);
        setInvoices(inv);
        setVendors(vend);
        setPOs(po);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const statusColor = {
    pending: "var(--text-secondary)",
    approved: "var(--green)",
    paid: "var(--blue)",
    flagged: "var(--red)",
    open: "var(--yellow)",
    closed: "var(--text-muted)",
  };

  if (loading) return <div style={{ padding: 24, color: "var(--text-muted)" }}>Loading finance data…</div>;

  const filteredInvoices = vendorFilter
    ? invoices.filter(i => i.vendor_name?.toLowerCase().includes(vendorFilter.toLowerCase()))
    : invoices;

  return (
    <div>
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-value stat-blue">{invoices.length}</div>
          <div className="stat-label">Total Invoices</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: "var(--red)" }}>
            {invoices.filter(i => i.status === "flagged").length}
          </div>
          <div className="stat-label">Flagged</div>
        </div>
        <div className="stat-card">
          <div className="stat-value stat-green">
            {invoices.filter(i => i.status === "paid").length}
          </div>
          <div className="stat-label">Paid</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{vendors.length}</div>
          <div className="stat-label">Vendors</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        {["invoices", "vendors", "purchase orders"].map(t => (
          <button
            key={t}
            className={`btn ${tab === t ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "invoices" && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
            <div className="card-title" style={{ margin: 0 }}>Invoices</div>
            <input
              style={{ width: 200 }}
              placeholder="Filter by vendor…"
              value={vendorFilter}
              onChange={e => setVendorFilter(e.target.value)}
            />
          </div>
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Vendor</th>
                <th>Date</th>
                <th>Due Date</th>
                <th>Amount (INR)</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredInvoices.map(inv => (
                <tr key={inv.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {isValidInvoiceNumber(inv.invoice_number) ? (
                      inv.invoice_number
                    ) : (
                      <span style={{ color: "var(--red)", fontStyle: "italic", fontWeight: 600 }}>
                        ⚠ Needs review ({inv.invoice_number || "Missing"})
                      </span>
                    )}
                  </td>
                  <td>{inv.vendor_name}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{inv.invoice_date || "—"}</td>
                  <td style={{ color: inv.due_date ? "var(--text-secondary)" : "var(--red)", fontSize: 12 }}>
                    {inv.due_date || "⚠ Missing"}
                  </td>
                  <td style={{ fontWeight: 600 }}>
                    ₹{parseFloat(inv.amount).toLocaleString("en-IN")}
                  </td>
                  <td>
                    <span style={{ color: statusColor[inv.status] || "var(--text-secondary)", fontWeight: 500 }}>
                      {inv.status}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredInvoices.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>No invoices found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "vendors" && (
        <div className="card">
          <div className="card-title">Vendor Master</div>
          <table className="evidence-table">
            <thead>
              <tr><th>Name</th><th>Code</th><th>Email</th><th>GSTIN</th><th>Active</th></tr>
            </thead>
            <tbody>
              {vendors.map(v => (
                <tr key={v.id}>
                  <td style={{ fontWeight: 500 }}>{v.name}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 12, color: "var(--accent-light)" }}>{v.code}</td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{v.contact_email || "—"}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{v.gstin || "—"}</td>
                  <td style={{ color: v.is_active ? "var(--green)" : "var(--red)" }}>
                    {v.is_active ? "✓" : "✗"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "purchase orders" && (
        <div className="card">
          <div className="card-title">Purchase Orders</div>
          <table className="evidence-table">
            <thead>
              <tr><th>PO #</th><th>Vendor</th><th>Date</th><th>Amount (INR)</th><th>Status</th></tr>
            </thead>
            <tbody>
              {pos.map(po => (
                <tr key={po.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>{po.po_number}</td>
                  <td>{po.vendor_name}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{po.po_date || "—"}</td>
                  <td style={{ fontWeight: 600 }}>₹{parseFloat(po.amount).toLocaleString("en-IN")}</td>
                  <td style={{ color: statusColor[po.status] }}>{po.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
