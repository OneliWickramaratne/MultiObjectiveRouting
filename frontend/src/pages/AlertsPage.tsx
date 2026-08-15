import { useEffect, useState } from "react";
import { Activity, Ambulance, CheckCircle2, Siren, UserCheck } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { CapacityForecastSummary, DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

// The destination leg's ETA is already computed and stored on the transfer
// (same route_payload_json used by the mission map and network map) — this
// just surfaces it as a reception-prep alert rather than adding any new
// backend logic or role.
function destinationEtaMinutes(transfer: TransferSummary): number | null {
  if (!transfer.route_payload_json) return null;
  try {
    const parsed = JSON.parse(transfer.route_payload_json) as {
      destination_route?: { estimated_minutes?: number };
      mission_route?: { estimated_minutes?: number };
    };
    const minutes = parsed.destination_route?.estimated_minutes ?? parsed.mission_route?.estimated_minutes;
    return typeof minutes === "number" ? minutes : null;
  } catch {
    return null;
  }
}

export function AlertsPage() {
  const { hospitals, backendOnline, user } = useAuth();
  const { t } = useLanguage();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [forecast, setForecast] = useState<CapacityForecastSummary | null>(null);
  const [selectedTransfer, setSelectedTransfer] = useState<TransferSummary | null>(null);
  const [transferEvents, setTransferEvents] = useState<TransferEventSummary[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  function pressureLabel(level: string) {
    return (t.enums.pressure as Record<string, string>)[level] ?? level;
  }

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
    (tr) => tr.urgency_class === "critical" && !["completed", "rejected"].includes(tr.status),
  );
  const incomingPatients = (dashboard?.transfers ?? []).filter((tr) => {
    if (tr.status !== "en_route_to_destination") return false;
    if (user?.role === "hospital_admin" && tr.destination_hospital_id !== user.hospital_id) return false;
    return true;
  });
  const offlineAmbulances = (dashboard?.ambulances ?? []).filter((a) => a.status === "offline");
  const pressuredHospitals = (forecast?.hospitals ?? []).filter(
    (h) => h.points[0] && ["high", "critical"].includes(h.points[0].pressure_level),
  );

  const hasAnyAlert = criticalTransfers.length > 0 || incomingPatients.length > 0 || offlineAmbulances.length > 0 || pressuredHospitals.length > 0 || !backendOnline;

  return (
    <div className="page">
      <div className={`alert-row ${backendOnline ? "tone-stable" : "tone-critical"}`}>
        {backendOnline ? <CheckCircle2 size={18} /> : <Activity size={18} />}
        <div>
          <strong>{backendOnline ? t.shell.networkConnected : t.shell.networkReconnecting}</strong>
          <span>{backendOnline ? t.shell.liveUpdatesOk : t.shell.actionsUnavailable}</span>
        </div>
      </div>

      {incomingPatients.map((tr) => {
        const eta = destinationEtaMinutes(tr);
        return (
          <button key={`incoming-${tr.id}`} type="button" className="alert-row tone-high alert-row-clickable" onClick={() => void openDetail(tr)}>
            <UserCheck size={18} />
            <div>
              <strong>
                {eta != null
                  ? t.alerts.patientArrivingIn.replace("{minutes}", String(Math.round(eta)))
                  : t.alerts.patientArrivingSoon}
              </strong>
              <span>{tr.patient_name ?? t.alerts.unnamedPatient} from {hospitalName(tr.origin_hospital_id)} → {hospitalName(tr.destination_hospital_id)}</span>
            </div>
          </button>
        );
      })}

      {criticalTransfers.map((tr) => (
        <button key={tr.id} type="button" className="alert-row tone-critical alert-row-clickable" onClick={() => void openDetail(tr)}>
          <Siren size={18} />
          <div>
            <strong>{t.alerts.criticalTransferInProgress}</strong>
            <span>{hospitalName(tr.origin_hospital_id)} → {hospitalName(tr.destination_hospital_id)}</span>
          </div>
        </button>
      ))}

      {pressuredHospitals.map((h) => (
        <div key={h.hospital_id} className={`alert-row tone-${h.points[0].pressure_level === "critical" ? "critical" : "high"}`}>
          <Activity size={18} />
          <div>
            <strong>{h.hospital_name} {t.alerts.underPressure.replace("{level}", pressureLabel(h.points[0].pressure_level))}</strong>
            <span>{h.recommended_action}</span>
          </div>
        </div>
      ))}

      {offlineAmbulances.length > 0 && (
        <div className="alert-row tone-high">
          <Ambulance size={18} />
          <div>
            <strong>{offlineAmbulances.length} {offlineAmbulances.length > 1 ? t.alerts.ambulanceOfflinePlural : t.alerts.ambulanceOfflineSingular}</strong>
            <span>{offlineAmbulances.map((a) => a.call_sign).join(", ")}</span>
          </div>
        </div>
      )}

      {!hasAnyAlert && (
        <div className="card empty-state" style={{ padding: "50px 20px" }}>
          {t.alerts.noActiveAlerts}
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
