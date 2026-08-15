import { useEffect, useState } from "react";
import { Ambulance, Bed, BarChart3, Loader2, Route as RouteIcon, Siren } from "lucide-react";
import { apiFetch } from "../lib/api";
import { simulationScenarioOptions, statusTone } from "../lib/constants";
import type { DashboardSummary, SimulationAnalyticsSummary } from "../types";

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

export function AnalyticsPage() {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [scenario, setScenario] = useState("evening_surge");
  const [hours, setHours] = useState("6");
  const [intensity, setIntensity] = useState("1");
  const [simLoading, setSimLoading] = useState(false);
  const [simulation, setSimulation] = useState<SimulationAnalyticsSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/admin/dashboard").then(async (r) => {
      if (r.ok && !cancelled) setDashboard(await r.json());
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  async function runSimulation() {
    setSimLoading(true);
    setError(null);
    try {
      const response = await apiFetch("/api/admin/simulation/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          duration_hours: Number(hours) || 6,
          intensity: Number(intensity) || 1,
        }),
      });
      if (!response.ok) throw new Error("Simulation request failed");
      setSimulation(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected simulation error");
    } finally {
      setSimLoading(false);
    }
  }

  const hospitals = dashboard?.hospitals ?? [];
  const ambulances = dashboard?.ambulances ?? [];
  const transfers = dashboard?.transfers ?? [];
  const totalBeds = hospitals.reduce((s, h) => s + h.total_beds, 0);
  const availableBeds = hospitals.reduce((s, h) => s + h.available_beds, 0);
  const occupancyPercent = totalBeds ? Math.round(((totalBeds - availableBeds) / totalBeds) * 100) : 0;
  const fleetReadiness = ambulances.length
    ? Math.round((ambulances.filter((a) => a.status === "available").length / ambulances.length) * 100)
    : 0;
  const activeTransfers = transfers.filter((t) => !["completed", "rejected"].includes(t.status)).length;
  const criticalQueue = transfers.filter((t) => t.urgency_class === "critical" && !["completed", "rejected"].includes(t.status)).length;

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <div className="label"><span className="icon-chip"><Bed size={15} /></span> Network occupancy</div>
          <div className="value">{occupancyPercent}%</div>
        </div>
        <div className="metric-card">
          <div className="label"><span className="icon-chip"><Ambulance size={15} /></span> Fleet readiness</div>
          <div className="value">{fleetReadiness}%</div>
        </div>
        <div className="metric-card">
          <div className="label"><span className="icon-chip"><RouteIcon size={15} /></span> Active transfers</div>
          <div className="value">{activeTransfers}</div>
        </div>
        <div className={`metric-card ${criticalQueue > 0 ? "spine tone-critical" : ""}`}>
          <div className="label"><span className="icon-chip tone-critical"><Siren size={15} /></span> Critical queue</div>
          <div className="value">{criticalQueue}</div>
        </div>
      </div>

      <div className="card card-pad">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h3>Scenario simulation</h3>
          <span className="hint">read-only operational stress test</span>
        </div>

        <div className="form-grid" style={{ marginBottom: 0 }}>
          <label className="form-field">
            Scenario
            <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {simulationScenarioOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </label>
          <label className="form-field">
            Duration (hours)
            <input type="number" min="1" max="24" value={hours} onChange={(e) => setHours(e.target.value)} />
          </label>
          <label className="form-field">
            Intensity
            <input type="number" min="0.25" max="3" step="0.25" value={intensity} onChange={(e) => setIntensity(e.target.value)} />
          </label>
        </div>

        <button type="button" className="btn-primary" onClick={runSimulation} disabled={simLoading} style={{ marginTop: 4 }}>
          {simLoading ? <Loader2 size={16} className="spin" /> : <BarChart3 size={16} />}
          Run simulation
        </button>

        {simulation ? (
          <>
            <div className={`sim-banner tone-${statusTone(simulation.network_pressure_level)}`} style={{ marginTop: 22 }}>
              <strong>{simulation.scenario_label}</strong>
              <span>{simulation.recommended_action}</span>
            </div>

            <div className="metric-grid" style={{ marginTop: 16, marginBottom: 4 }}>
              <div className="metric-card">
                <div className="label">Transfers</div>
                <div className="value">{simulation.simulated_transfers}</div>
              </div>
              <div className="metric-card">
                <div className="label">Critical</div>
                <div className="value">{simulation.critical_transfers}</div>
              </div>
              <div className={`metric-card ${simulation.ambulance_gap > 0 ? "spine tone-high" : ""}`}>
                <div className="label">Ambulance gap</div>
                <div className="value">{simulation.ambulance_gap}</div>
              </div>
              <div className={`metric-card ${simulation.total_shortage_beds > 0 ? "spine tone-critical" : ""}`}>
                <div className="label">Bed shortage</div>
                <div className="value">{simulation.total_shortage_beds}</div>
              </div>
            </div>

            <div className="section-head">
              <h3>Hospital impact</h3>
            </div>
            <div className="row-list">
              {simulation.hospital_impacts.slice(0, 8).map((impact) => (
                <div key={impact.hospital_id} className={`row-card spine tone-${statusTone(impact.pressure_level)}`}>
                  <div className="row-main">
                    <span className="row-title">{impact.hospital_name}</span>
                    <span className="row-sub">
                      {impact.projected_arrivals} arrivals · {impact.projected_releases} releases · {impact.predicted_available_beds} beds after scenario
                    </span>
                  </div>
                  <span className={`pill tone-${statusTone(impact.pressure_level)}`}>{formatStatus(impact.pressure_level)}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state" style={{ marginTop: 20 }}>Run a scenario to see simulated ICU and fleet pressure.</div>
        )}
      </div>
    </div>
  );
}
