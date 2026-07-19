import { useEffect, useState } from "react";
import { Activity, Ambulance, CheckCircle2, Siren } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useAuth } from "../state/AuthContext";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { CapacityForecastSummary, DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

export function AlertsPage() {
  const { hospitals, backendOnline } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [forecast, setForecast] = useState<CapacityForecastSummary | null>(null);
  const [selectedTransfer, setSelectedTransfer] = useState<TransferSummary | null>(null);
  const [transferEvents, setTransferEvents] = useState<TransferEventSummary[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [dashRes, forecastRes] = await Promise.all([
        apiFetch("/api/admin/dashboard"),
        apiFetch("/api/admin/capacity/forecast"),
      ]);
      if (!cancelled && dashRes.ok) setDashboard(await dashRes.json());
      if (!cancelled && forecastRes.ok) setForecast(await forecastRes.json());
    }
    void load();
    const interval = window.setInterval(() => void load(), 5000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  function hospitalName(id: string) {
    return hospitals.find((h) => h.id === id)?.name ?? `Hospital ${id}`;
  }

  async function openDetail(transfer: TransferSummary) {
    setSelectedTransfer(transfer);
    setTransferEvents([]);
    setEventsLoading(true);
    try {
      const response = await apiFetch(`/api/admin/transfers/${transfer.id}/events`);
      if (response.ok) setTransferEvents(await response.json());
    } finally {
      setEventsLoading(false);
    }
  }

  const criticalTransfers = (dashboard?.transfers ?? []).filter(
    (t) => t.urgency_class === "critical" && !["completed", "rejected"].includes(t.status),
  );
  const offlineAmbulances = (dashboard?.ambulances ?? []).filter((a) => a.status === "offline");
  const pressuredHospitals = (forecast?.hospitals ?? []).filter(
    (h) => h.points[0] && ["high", "critical"].includes(h.points[0].pressure_level),
  );

  const hasAnyAlert = criticalTransfers.length > 0 || offlineAmbulances.length > 0 || pressuredHospitals.length > 0 || !backendOnline;

  return (
    <div className="page">
      <div className={`alert-row ${backendOnline ? "tone-stable" : "tone-critical"}`}>
        {backendOnline ? <CheckCircle2 size={18} /> : <Activity size={18} />}
        <div>
          <strong>{backendOnline ? "Hospital network connected" : "Hospital network reconnecting"}</strong>
          <span>{backendOnline ? "Live updates are operational." : "Actions are temporarily unavailable."}</span>
        </div>
      </div>

      {criticalTransfers.map((t) => (
        <button key={t.id} type="button" className="alert-row tone-critical alert-row-clickable" onClick={() => void openDetail(t)}>
          <Siren size={18} />
          <div>
            <strong>Critical transfer in progress</strong>
            <span>{hospitalName(t.origin_hospital_id)} → {hospitalName(t.destination_hospital_id)}</span>
          </div>
        </button>
      ))}

      {pressuredHospitals.map((h) => (
        <div key={h.hospital_id} className={`alert-row tone-${h.points[0].pressure_level === "critical" ? "critical" : "high"}`}>
          <Activity size={18} />
          <div>
            <strong>{h.hospital_name} under {h.points[0].pressure_level} pressure</strong>
            <span>{h.recommended_action}</span>
          </div>
        </div>
      ))}

      {offlineAmbulances.length > 0 && (
        <div className="alert-row tone-high">
          <Ambulance size={18} />
          <div>
            <strong>{offlineAmbulances.length} ambulance{offlineAmbulances.length > 1 ? "s" : ""} offline</strong>
            <span>{offlineAmbulances.map((a) => a.call_sign).join(", ")}</span>
          </div>
        </div>
      )}

      {!hasAnyAlert && (
        <div className="card empty-state" style={{ padding: "50px 20px" }}>
          No active alerts. The network is operating normally.
        </div>
      )}

      <TransferDetailDrawer
        transfer={selectedTransfer}
        hospitals={hospitals}
        events={transferEvents}
        eventsLoading={eventsLoading}
        onClose={() => setSelectedTransfer(null)}
      />
    </div>
  );
}
