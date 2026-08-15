import { useEffect, useState } from "react";
import { Ambulance, Check, Info, X } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import { ConfirmModal } from "../components/ConfirmModal";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { BlockingModal, DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

const STAGES = [
  "pending_destination_acceptance",
  "ambulance_assigned",
  "ambulance_en_route_to_pickup",
  "en_route_to_destination",
  "completed",
];

function transferStage(transfer: TransferSummary) {
  if (transfer.status === "rejected" || transfer.status === "cancelled") return -1;
  const index = STAGES.indexOf(transfer.status);
  if (index >= 0) return index;
  if (transfer.status === "accepted_pending_ambulance") return 1;
  return 0;
}

function canAcceptTransfer(transfer: TransferSummary) {
  return transfer.status === "pending_destination_acceptance";
}
function canAssignAmbulance(transfer: TransferSummary) {
  return transfer.status === "accepted_pending_ambulance";
}

export function RequestsPage() {
  const { user, hospitals } = useAuth();
  const { t } = useLanguage();
  const isSuperAdmin = user?.role === "super_admin";
  const activeHospitalId = user?.hospital_id ?? null;

  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<BlockingModal | null>(null);
  const [selectedTransfer, setSelectedTransfer] = useState<TransferSummary | null>(null);
  const [transferEvents, setTransferEvents] = useState<TransferEventSummary[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

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
        if (!cancelled && !silent) setError(err instanceof Error ? err.message : "Unable to load requests");
      }
    }
    void load(false);
    const interval = window.setInterval(() => void load(true), 3000);
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

  async function executeAction(transferId: string, action: "accept" | "reject" | "assign-ambulance") {
    const response = await apiFetch(`/api/admin/transfers/${transferId}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: action === "assign-ambulance" ? undefined : JSON.stringify({ notes: action }),
    });
    if (!response.ok) {
      let detail = `${action.replace("-", " ")} failed`;
      try {
        const payload = await response.json();
        if (payload?.detail) detail = payload.detail;
      } catch {
        // Response wasn't JSON; fall back to the generic message.
      }
      setError(detail);
      setModal(null);
      return;
    }
    const updated: TransferSummary = await response.json();
    const response2 = await apiFetch("/api/admin/dashboard");
    if (response2.ok) setDashboard(await response2.json());
    if (action === "accept") {
      setModal({
        title: t.requests.acceptedTitle,
        message: updated.ambulance_id
          ? t.requests.acceptedWithAmbulance.replace("{ambulanceId}", updated.ambulance_id)
          : t.requests.acceptedWaitingAmbulance,
        tone: "success",
        confirmLabel: t.requests.continueLabel,
      });
    } else {
      setModal(null);
    }
  }

  function confirmAccept(transfer: TransferSummary) {
    setModal({
      title: t.requests.acceptModalTitle,
      message: t.requests.acceptModalMessage
        .replace("{origin}", hospitalName(transfer.origin_hospital_id))
        .replace("{destination}", hospitalName(transfer.destination_hospital_id)),
      tone: "warning",
      confirmLabel: t.requests.acceptConfirmLabel,
      cancelLabel: t.common.cancel,
      onConfirm: () => executeAction(transfer.id, "accept"),
    });
  }

  function confirmReject(transfer: TransferSummary) {
    setModal({
      title: t.requests.rejectModalTitle,
      message: t.requests.rejectModalMessage.replace("{origin}", hospitalName(transfer.origin_hospital_id)),
      tone: "warning",
      confirmLabel: t.requests.rejectConfirmLabel,
      cancelLabel: t.common.cancel,
      onConfirm: () => executeAction(transfer.id, "reject"),
    });
  }

  const transfers = dashboard?.transfers ?? [];
  const incoming = transfers.filter((tr) => activeHospitalId && tr.destination_hospital_id === activeHospitalId);
  const outgoing = transfers.filter((tr) => activeHospitalId && tr.origin_hospital_id === activeHospitalId);

  function urgencyLabel(level: string) {
    return (t.enums.urgency as Record<string, string>)[level] ?? level;
  }

  function TransferCard({ transfer }: { transfer: TransferSummary }) {
    const stage = transferStage(transfer);
    const stopped = transfer.status === "rejected" || transfer.status === "cancelled";
    const timelineLabels = [
      t.requests.timelineRequest,
      t.requests.timelineAssigned,
      t.requests.timelinePickup,
      t.requests.timelineDestination,
      t.requests.timelineDone,
    ];
    return (
      <div className={`transfer-card spine tone-${statusTone(transfer.urgency_class)}`}>
        <div className="transfer-card-head">
          <div>
            <strong>{hospitalName(transfer.origin_hospital_id)} → {hospitalName(transfer.destination_hospital_id)}</strong>
            <span className="row-sub">{transfer.required_icu_type} · {transfer.patient_name ?? t.requests.unnamed} · {transfer.patient_condition}</span>
          </div>
          <span className={`pill tone-${statusTone(transfer.urgency_class)}`}>{urgencyLabel(transfer.urgency_class)}</span>
        </div>

        <div className="transfer-timeline">
          {timelineLabels.map((label, index) => (
            <span
              key={label}
              className={
                stopped ? (index === 0 ? "tl-stopped" : "tl-idle")
                : transfer.status === "completed" ? "tl-done"
                : index < stage ? "tl-done"
                : index === stage ? "tl-current"
                : "tl-idle"
              }
            >
              {label}
            </span>
          ))}
        </div>

        <div className="transfer-card-actions">
          <button type="button" className="btn-secondary" onClick={() => void openDetail(transfer)}>
            <Info size={13} /> {t.requests.details}
          </button>
          {canAcceptTransfer(transfer) && (
            <>
              <button type="button" className="btn-secondary tone-moderate" onClick={() => confirmAccept(transfer)}>
                <Check size={13} /> {t.requests.accept}
              </button>
              <button type="button" className="btn-secondary tone-critical" onClick={() => confirmReject(transfer)}>
                <X size={13} /> {t.requests.reject}
              </button>
            </>
          )}
          {isSuperAdmin && canAssignAmbulance(transfer) && (
            <button type="button" className="btn-secondary" onClick={() => executeAction(transfer.id, "assign-ambulance")}>
              <Ambulance size={13} /> {t.requests.assignAmbulance}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      {isSuperAdmin ? (
        <>
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>{t.requests.transferQueueHeading}</h3>
            <span className="hint">{transfers.length} {t.requests.totalSuffix}</span>
          </div>
          <div className="row-list">
            {transfers.length ? transfers.map((tr) => <TransferCard key={tr.id} transfer={tr} />) : (
              <div className="card empty-state">{t.requests.noNetworkRequests}</div>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>{t.requests.incomingHeading}</h3>
            <span className="hint">{t.requests.awaitingDecision}</span>
          </div>
          <div className="row-list">
            {incoming.length ? incoming.map((tr) => <TransferCard key={tr.id} transfer={tr} />) : (
              <div className="card empty-state">{t.requests.noIncoming}</div>
            )}
          </div>

          <div className="section-head">
            <h3>{t.requests.outgoingHeading}</h3>
            <span className="hint">{t.requests.sentFromHospital}</span>
          </div>
          <div className="row-list">
            {outgoing.length ? outgoing.map((tr) => <TransferCard key={tr.id} transfer={tr} />) : (
              <div className="card empty-state">{t.requests.noOutgoing}</div>
            )}
          </div>
        </>
      )}

      <TransferDetailDrawer
        transfer={selectedTransfer}
        hospitals={hospitals}
        events={transferEvents}
        eventsLoading={eventsLoading}
        onClose={() => setSelectedTransfer(null)}
      />
      <ConfirmModal modal={modal} onClose={() => setModal(null)} />
    </div>
  );
}
