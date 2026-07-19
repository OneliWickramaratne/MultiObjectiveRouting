import { useEffect, useState } from "react";
import { Ambulance, Settings2 } from "lucide-react";
import { apiFetch } from "../lib/api";
import { ambulanceStatusOptions } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import type { AmbulanceSummary, DashboardSummary } from "../types";

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

// Ambulance status → triage-spine tone.
function ambulanceTone(status: string) {
  if (status === "available") return "stable";
  if (status === "offline") return "critical";
  if (status === "assigned" || status === "en_route" || status === "transporting") return "high";
  return "offline"; // returning / repositioning
}

export function FleetPage() {
  const { hospitals } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [managingId, setManagingId] = useState<string | null>(null);

  async function load(silent: boolean) {
    try {
      const response = await apiFetch("/api/admin/dashboard");
      if (!response.ok) throw new Error("Dashboard request failed");
      setDashboard(await response.json());
      setError(null);
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Unable to load fleet data");
    }
  }

  useEffect(() => {
    void load(false);
    const interval = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(interval);
  }, []);

  async function updateStatus(ambulance: AmbulanceSummary, status: string) {
    const response = await apiFetch(`/api/admin/ambulances/${ambulance.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      setError("Ambulance status update failed");
      return;
    }
    await load(true);
  }

  function hospitalName(id: string | null) {
    if (!id) return "Central pool";
    return hospitals.find((h) => h.id === id)?.name ?? `Hospital ${id}`;
  }

  const ambulances = dashboard?.ambulances ?? [];
  const available = ambulances.filter((a) => a.status === "available").length;

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="metric-grid">
        <div className="metric-card spine tone-stable">
          <div className="label"><span className="icon-chip"><Ambulance size={15} /></span> Available</div>
          <div className="value">{available}<span style={{ fontSize: 15, color: "var(--text-faint)" }}> / {ambulances.length}</span></div>
        </div>
        <div className="metric-card spine tone-high">
          <div className="label"><span className="icon-chip tone-high"><Ambulance size={15} /></span> On mission</div>
          <div className="value">{ambulances.filter((a) => ["assigned", "en_route", "transporting"].includes(a.status)).length}</div>
        </div>
        <div className="metric-card spine tone-offline">
          <div className="label"><span className="icon-chip tone-offline"><Ambulance size={15} /></span> Repositioning</div>
          <div className="value">{ambulances.filter((a) => ["returning", "repositioning"].includes(a.status)).length}</div>
        </div>
        <div className="metric-card spine tone-critical">
          <div className="label"><span className="icon-chip tone-critical"><Ambulance size={15} /></span> Offline</div>
          <div className="value">{ambulances.filter((a) => a.status === "offline").length}</div>
        </div>
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <h3>Ambulance pool</h3>
        <span className="hint">{ambulances.length} vehicles</span>
      </div>

      <div className="row-list">
        {ambulances.length ? ambulances.map((ambulance) => (
          <div key={ambulance.id} className={`row-card spine tone-${ambulanceTone(ambulance.status)}`}>
            <div className="row-main">
              <span className="row-title">{ambulance.call_sign}</span>
              <span className="row-sub">Base: {hospitalName(ambulance.base_hospital_id)}</span>
            </div>
            <div className="row-figures">
              <span className={`pill tone-${ambulanceTone(ambulance.status)}`}>{formatStatus(ambulance.status)}</span>
              {managingId === ambulance.id ? (
                <select
                  aria-label={`${ambulance.call_sign} status`}
                  value={ambulance.status}
                  autoFocus
                  onBlur={() => setManagingId(null)}
                  onChange={(e) => { void updateStatus(ambulance, e.target.value); setManagingId(null); }}
                  style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 12.5 }}
                >
                  {ambulanceStatusOptions.map((status) => (
                    <option key={status} value={status}>{formatStatus(status)}</option>
                  ))}
                </select>
              ) : (
                <button type="button" className="btn-secondary" onClick={() => setManagingId(ambulance.id)}>
                  <Settings2 size={13} /> Manage
                </button>
              )}
            </div>
          </div>
        )) : (
          <div className="card empty-state">No ambulance data available.</div>
        )}
      </div>
    </div>
  );
}
