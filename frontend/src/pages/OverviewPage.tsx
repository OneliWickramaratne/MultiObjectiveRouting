import { useEffect, useState } from "react";
import { Activity, Ambulance, Bed, Building2, Route as RouteIcon } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import type { CapacityForecastSummary, DashboardSummary } from "../types";

export function OverviewPage() {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [forecast, setForecast] = useState<CapacityForecastSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load(silent: boolean) {
      try {
        const response = await apiFetch("/api/admin/dashboard");
        if (!response.ok) throw new Error("Dashboard request failed");
        const data: DashboardSummary = await response.json();
        if (!cancelled) {
          setDashboard(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !silent) {
          setError(err instanceof Error ? err.message : "Unable to load dashboard");
        }
      }
      try {
        const response = await apiFetch("/api/admin/capacity/forecast");
        if (response.ok) {
          const data: CapacityForecastSummary = await response.json();
          if (!cancelled) setForecast(data);
        }
      } catch {
        // Capacity forecast is supplementary; dashboard error already surfaced above.
      }
    }

    void load(false);
    const interval = window.setInterval(() => void load(true), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const hospitals = dashboard?.hospitals ?? [];
  const ambulances = dashboard?.ambulances ?? [];
  const transfers = dashboard?.transfers ?? [];

  const availableBeds = hospitals.reduce((sum, h) => sum + h.available_beds, 0);
  const totalBeds = hospitals.reduce((sum, h) => sum + h.total_beds, 0);
  const availableAmbulances = ambulances.filter((a) => a.status === "available").length;
  const activeTransfers = transfers.filter((t) => !["completed", "rejected"].includes(t.status)).length;

  const recentTransfers = [...transfers]
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    .slice(0, 6);

  const pressureRows = (forecast?.hospitals ?? [])
    .map((h) => ({ ...h, nearPoint: h.points[0] }))
    .filter((h) => h.nearPoint)
    .sort((a, b) => b.nearPoint.pressure_score - a.nearPoint.pressure_score)
    .slice(0, 6);

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="metric-grid">
        <div className={`metric-card spine tone-${forecast ? statusTone(forecast.network_pressure_level) : "offline"}`}>
          <div className="label"><span className="icon-chip"><Building2 size={15} /></span> Hospitals</div>
          <div className="value">{hospitals.length}</div>
          <div className="sub">across the Colombo network</div>
        </div>
        <div className="metric-card spine tone-stable">
          <div className="label"><span className="icon-chip"><Bed size={15} /></span> ICU beds open</div>
          <div className="value">{availableBeds}<span style={{ fontSize: 15, color: "var(--text-faint)" }}> / {totalBeds}</span></div>
          <div className="sub">{totalBeds ? Math.round((availableBeds / totalBeds) * 100) : 0}% available</div>
        </div>
        <div className="metric-card spine tone-stable">
          <div className="label"><span className="icon-chip"><Ambulance size={15} /></span> Ambulances</div>
          <div className="value">{availableAmbulances}<span style={{ fontSize: 15, color: "var(--text-faint)" }}> / {ambulances.length}</span></div>
          <div className="sub">ready for dispatch</div>
        </div>
        <div className={`metric-card spine ${activeTransfers > 0 ? "tone-high" : "tone-stable"}`}>
          <div className="label"><span className="icon-chip"><RouteIcon size={15} /></span> Active transfers</div>
          <div className="value">{activeTransfers}</div>
          <div className="sub">in progress right now</div>
        </div>
      </div>

      <div className="section-head">
        <h3>Network pressure</h3>
        <span className="hint">
          {forecast ? forecast.network_recommended_action : "Loading forecast…"}
        </span>
      </div>
      <div className="row-list">
        {pressureRows.length === 0 && (
          <div className="card empty-state">No capacity forecast data yet.</div>
        )}
        {pressureRows.map((h) => (
          <div key={h.hospital_id} className={`row-card spine tone-${statusTone(h.nearPoint.pressure_level)}`}>
            <div className="row-main">
              <span className="row-title">{h.hospital_name}</span>
              <span className="row-sub">{h.recommended_action}</span>
            </div>
            <div className="row-figures">
              <div className="figure">
                <div className="n">{h.current_available_beds}/{h.total_beds}</div>
                <div className="l">Open beds</div>
              </div>
              <div className="figure">
                <div className="n">{h.inbound_transfers}</div>
                <div className="l">Inbound</div>
              </div>
              <span className={`pill tone-${statusTone(h.nearPoint.pressure_level)}`}>{h.nearPoint.pressure_level}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section-head">
        <h3>Recent transfers</h3>
        <span className="hint"><Activity size={12} style={{ verticalAlign: "-2px" }} /> live</span>
      </div>
      <div className="row-list">
        {recentTransfers.length === 0 && (
          <div className="card empty-state">No transfer activity yet.</div>
        )}
        {recentTransfers.map((t) => {
          const origin = hospitals.find((h) => h.id === t.origin_hospital_id)?.name ?? t.origin_hospital_id;
          const destination = hospitals.find((h) => h.id === t.destination_hospital_id)?.name ?? t.destination_hospital_id;
          return (
            <div key={t.id} className={`row-card spine tone-${statusTone(t.urgency_class)}`}>
              <div className="row-main">
                <span className="row-title">{origin} → {destination}</span>
                <span className="row-sub">{t.patient_condition} · {t.required_icu_type}</span>
              </div>
              <div className="row-figures">
                <span className={`pill tone-${statusTone(t.urgency_class)}`}>{t.urgency_class}</span>
                <span className="pill tone-offline">{t.status.split("_").join(" ")}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
