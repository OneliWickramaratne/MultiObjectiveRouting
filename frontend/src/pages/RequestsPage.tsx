import { useEffect, useState } from "react";
import { Ambulance, Check, Info, X } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { ConfirmModal } from "../components/ConfirmModal";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { BlockingModal, DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

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
      return;
    }
    const updated: TransferSummary = await response.json();
    const response2 = await apiFetch("/api/admin/dashboard");
    if (response2.ok) setDashboard(await response2.json());
    if (action === "accept") {
      setModal({
        title: "Request accepted",
        message: updated.ambulance_id
          ? `Transfer accepted. Bed reserved and ambulance ${updated.ambulance_id} assigned.`
          : "Transfer accepted. Bed reserved; waiting for an available ambulance.",
        tone: "success",
        confirmLabel: "Continue",
      });
    }
  }

  function confirmAccept(transfer: TransferSummary) {
    setModal({
      title: "Accept transfer request?",
      message: `Accept transfer from ${hospitalName(transfer.origin_hospital_id)} to ${hospitalName(transfer.destination_hospital_id)}? This reserves one ICU bed and auto-assigns an ambulance if one is available.`,
      tone: "warning",
      confirmLabel: "Accept request",
      cancelLabel: "Cancel",
      onConfirm: () => executeAction(transfer.id, "accept"),
    });
  }

  function confirmReject(transfer: TransferSummary) {
    setModal({
      title: "Reject transfer request?",
      message: `Reject the transfer from ${hospitalName(transfer.origin_hospital_id)}? The sending hospital will need to find another destination.`,
      tone: "warning",
      confirmLabel: "Reject request",
      cancelLabel: "Cancel",
      onConfirm: () => executeAction(transfer.id, "reject"),
    });
  }

  const transfers = dashboard?.transfers ?? [];
  const incoming = transfers.filter((t) => activeHospitalId && t.destination_hospital_id === activeHospitalId);
  const outgoing = transfers.filter((t) => activeHospitalId && t.origin_hospital_id === activeHospitalId);

  function TransferCard({ transfer }: { transfer: TransferSummary }) {
    const stage = transferStage(transfer);
    const stopped = transfer.status === "rejected" || transfer.status === "cancelled";
    return (
      <div className={`transfer-card spine tone-${statusTone(transfer.urgency_class)}`}>
        <div className="transfer-card-head">
          <div>
            <strong>{hospitalName(transfer.origin_hospital_id)} → {hospitalName(transfer.destination_hospital_id)}</strong>
            <span className="row-sub">{transfer.required_icu_type} · {transfer.patient_name ?? "Unnamed"} · {transfer.patient_condition}</span>
          </div>
          <span className={`pill tone-${statusTone(transfer.urgency_class)}`}>{transfer.urgency_class}</span>
        </div>

        <div className="transfer-timeline">
          {["Request", "Assigned", "Pickup", "Destination", "Done"].map((label, index) => (
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
            <Info size={13} /> Details
          </button>
          {canAcceptTransfer(transfer) && (
            <>
              <button type="button" className="btn-secondary tone-moderate" onClick={() => confirmAccept(transfer)}>
                <Check size={13} /> Accept
              </button>
              <button type="button" className="btn-secondary tone-critical" onClick={() => confirmReject(transfer)}>
                <X size={13} /> Reject
              </button>
            </>
          )}
          {isSuperAdmin && canAssignAmbulance(transfer) && (
            <button type="button" className="btn-secondary" onClick={() => executeAction(transfer.id, "assign-ambulance")}>
              <Ambulance size={13} /> Assign ambulance
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
            <h3>Transfer command queue</h3>
            <span className="hint">{transfers.length} total</span>
          </div>
          <div className="row-list">
            {transfers.length ? transfers.map((t) => <TransferCard key={t.id} transfer={t} />) : (
              <div className="card empty-state">No transfer requests in the network.</div>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>Incoming requests</h3>
            <span className="hint">awaiting your decision</span>
          </div>
          <div className="row-list">
            {incoming.length ? incoming.map((t) => <TransferCard key={t.id} transfer={t} />) : (
              <div className="card empty-state">No incoming transfer requests.</div>
            )}
          </div>

          <div className="section-head">
            <h3>Outgoing transfers</h3>
            <span className="hint">sent from your hospital</span>
          </div>
          <div className="row-list">
            {outgoing.length ? outgoing.map((t) => <TransferCard key={t.id} transfer={t} />) : (
              <div className="card empty-state">No outgoing transfer requests.</div>
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
