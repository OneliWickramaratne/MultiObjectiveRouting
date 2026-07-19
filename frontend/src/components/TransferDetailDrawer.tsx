import { X } from "lucide-react";
import { statusTone } from "../lib/constants";
import type { DispatchPayload, Hospital, TransferEventSummary, TransferSummary } from "../types";

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

function formatDateTime(value?: string) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function formatVitals(value: Record<string, unknown> | null | undefined) {
  if (!value) return "";
  return Object.entries(value).map(([key, item]) => `${key}: ${String(item)}`).join(", ");
}

function parseDispatchPayload(transfer?: TransferSummary | null): DispatchPayload | null {
  if (!transfer?.route_payload_json) return null;
  try {
    const parsed = JSON.parse(transfer.route_payload_json) as { dispatch?: DispatchPayload };
    return parsed.dispatch ?? null;
  } catch {
    return null;
  }
}

export function TransferDetailDrawer({
  transfer,
  hospitals,
  events,
  eventsLoading,
  onClose,
}: {
  transfer: TransferSummary | null;
  hospitals: Hospital[];
  events: TransferEventSummary[];
  eventsLoading: boolean;
  onClose: () => void;
}) {
  if (!transfer) return null;

  const hospitalName = (id: string) => hospitals.find((h) => h.id === id)?.name ?? `Hospital ${id}`;
  const dispatch = parseDispatchPayload(transfer);

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <aside className="drawer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <h2>Transfer detail</h2>
            <p>{hospitalName(transfer.origin_hospital_id)} → {hospitalName(transfer.destination_hospital_id)}</p>
          </div>
          <button type="button" className="modal-close" style={{ position: "static" }} onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="drawer-body">
          <div className="detail-grid">
            <div><span>Status</span><strong>{formatStatus(transfer.status)}</strong></div>
            <div><span>Urgency</span><strong className={`pill tone-${statusTone(transfer.urgency_class)}`}>{transfer.urgency_class}</strong></div>
            <div><span>Required ICU</span><strong>{transfer.required_icu_type}</strong></div>
            <div><span>Ambulance</span><strong>{transfer.ambulance_id ?? "Not assigned"}</strong></div>
            <div><span>Assigned bed</span><strong>{transfer.assigned_bed_id ? transfer.assigned_bed_id.slice(0, 8) : "Not assigned"}</strong></div>
          </div>

          {dispatch && (
            <>
              <h3>Dispatch decision</h3>
              <div className="detail-grid">
                <div><span>Model</span><strong>{dispatch.model ?? "dispatch model"}</strong></div>
                <div><span>Score</span><strong>{dispatch.score?.toFixed?.(2) ?? "-"}</strong></div>
                <div><span>Pickup ETA</span><strong>{dispatch.estimated_pickup_minutes ?? "-"} min</strong></div>
                <div><span>Pickup risk</span><strong>{dispatch.pickup_risk_score?.toFixed?.(2) ?? "-"}</strong></div>
                <div><span>Coverage impact</span><strong>{dispatch.coverage_penalty?.toFixed?.(2) ?? "-"}</strong></div>
              </div>
              {dispatch.explanation?.length ? (
                <div className="dispatch-reasons">
                  {dispatch.explanation.map((reason) => <span key={reason} className="pill tone-offline">{reason}</span>)}
                </div>
              ) : null}
            </>
          )}

          <h3>Patient packet</h3>
          <div className="detail-grid">
            <div><span>Name</span><strong>{transfer.patient_name ?? "Unnamed patient"}</strong></div>
            <div><span>Identifier</span><strong>{transfer.patient_identifier_value ?? "-"}</strong></div>
            <div><span>Age / sex</span><strong>{transfer.patient_age ?? "-"} / {transfer.patient_sex ?? "-"}</strong></div>
            <div><span>Blood type</span><strong>{transfer.patient_blood_type ?? "-"}</strong></div>
            <div><span>Condition</span><strong>{transfer.patient_condition}</strong></div>
            <div><span>Diagnosis</span><strong>{transfer.patient_diagnosis ?? "-"}</strong></div>
            <div className="full"><span>Vitals</span><strong>{formatVitals(transfer.patient_vitals) || "-"}</strong></div>
            <div className="full"><span>Medications</span><strong>{transfer.patient_medications?.length ? transfer.patient_medications.join(", ") : "-"}</strong></div>
            <div className="full"><span>Allergies / alerts</span><strong>{transfer.patient_allergies ?? "None recorded"}</strong></div>
            <div><span>Infection risk</span><strong>{transfer.patient_infection_risk ?? "none"}</strong></div>
            <div><span>Isolation</span><strong>{transfer.patient_isolation_required ? "Required" : "Not required"}</strong></div>
            <div className="full"><span>Emergency contact</span><strong>{transfer.patient_emergency_contact ?? "-"}</strong></div>
          </div>

          <h3>Event timeline</h3>
          {eventsLoading ? (
            <div className="empty-state">Loading timeline…</div>
          ) : events.length ? (
            <div className="event-list">
              {events.map((event) => (
                <div className="event-row" key={event.id}>
                  <div className="event-dot" />
                  <div>
                    <strong>{formatStatus(event.event_type)}</strong>
                    <span>{event.message}</span>
                    <small>
                      {formatDateTime(event.created_at)}
                      {event.actor_user_id ? ` · ${event.actor_user_id}` : ""}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">No timeline events recorded yet.</div>
          )}
        </div>
      </aside>
    </div>
  );
}
