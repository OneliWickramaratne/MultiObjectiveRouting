import { useEffect, useState } from "react";
import { Activity, Ambulance, Bed, Building2, Route as RouteIcon } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useLanguage } from "../i18n/LanguageContext";
import type { CapacityForecastSummary, DashboardSummary } from "../types";

export function OverviewPage() {
  const { t } = useLanguage();
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

  function pressureLabel(level: string) {
    return (t.enums.pressure as Record<string, string>)[level] ?? level;
  }
  function urgencyLabel(level: string) {
    return (t.enums.urgency as Record<string, string>)[level] ?? level;
  }
  function statusLabel(status: string) {
    return (t.enums.transferStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="metric-grid">
        <div className={`metric-card spine tone-${forecast ? statusTone(forecast.network_pressure_level) : "offline"}`}>
          <div className="label"><span className="icon-chip"><Building2 size={15} /></span> {t.overview.hospitalsCard}</div>
          <div className="value">{hospitals.length}</div>
          <div className="sub">{t.overview.acrossNetwork}</div>
        </div>
        <div className="metric-card spine tone-stable">
          <div className="label"><span className="icon-chip"><Bed size={15} /></span> {t.overview.icuBedsOpenCard}</div>
          <div className="value">{availableBeds}<span style={{ fontSize: 15, color: "var(--text-faint)" }}> / {totalBeds}</span></div>
          <div className="sub">{totalBeds ? Math.round((availableBeds / totalBeds) * 100) : 0}% {t.overview.percentAvailable}</div>
        </div>
        <div className="metric-card spine tone-stable">
          <div className="label"><span className="icon-chip"><Ambulance size={15} /></span> {t.overview.ambulancesCard}</div>
          <div className="value">{availableAmbulances}<span style={{ fontSize: 15, color: "var(--text-faint)" }}> / {ambulances.length}</span></div>
          <div className="sub">{t.overview.readyForDispatch}</div>
        </div>
        <div className={`metric-card spine ${activeTransfers > 0 ? "tone-high" : "tone-stable"}`}>
          <div className="label"><span className="icon-chip"><RouteIcon size={15} /></span> {t.overview.activeTransfersCard}</div>
          <div className="value">{activeTransfers}</div>
          <div className="sub">{t.overview.inProgressNow}</div>
        </div>
      </div>

      <div className="section-head">
        <h3>{t.overview.networkPressureHeading}</h3>
        <span className="hint">
          {forecast ? forecast.network_recommended_action : t.overview.loadingForecast}
        </span>
      </div>
      <div className="row-list">
        {pressureRows.length === 0 && (
          <div className="card empty-state">{t.overview.noForecastData}</div>
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
                <div className="l">{t.overview.openBeds}</div>
              </div>
              <div className="figure">
                <div className="n">{h.inbound_transfers}</div>
                <div className="l">{t.overview.inbound}</div>
              </div>
              <span className={`pill tone-${statusTone(h.nearPoint.pressure_level)}`}>{pressureLabel(h.nearPoint.pressure_level)}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section-head">
        <h3>{t.overview.recentTransfersHeading}</h3>
        <span className="hint"><Activity size={12} style={{ verticalAlign: "-2px" }} /> {t.overview.live}</span>
      </div>
      <div className="row-list">
        {recentTransfers.length === 0 && (
          <div className="card empty-state">{t.overview.noTransferActivity}</div>
        )}
        {recentTransfers.map((t2) => {
          const origin = hospitals.find((h) => h.id === t2.origin_hospital_id)?.name ?? t2.origin_hospital_id;
          const destination = hospitals.find((h) => h.id === t2.destination_hospital_id)?.name ?? t2.destination_hospital_id;
          return (
            <div key={t2.id} className={`row-card spine tone-${statusTone(t2.urgency_class)}`}>
              <div className="row-main">
                <span className="row-title">{origin} → {destination}</span>
                <span className="row-sub">{t2.patient_condition} · {t2.required_icu_type}</span>
              </div>
              <div className="row-figures">
                <span className={`pill tone-${statusTone(t2.urgency_class)}`}>{urgencyLabel(t2.urgency_class)}</span>
                <span className="pill tone-offline">{statusLabel(t2.status)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
