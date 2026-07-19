import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

const STATUS_FILTERS = [
  "all",
  "pending_destination_acceptance",
  "accepted_pending_ambulance",
  "ambulance_assigned",
  "ambulance_en_route_to_pickup",
  "en_route_to_destination",
  "completed",
  "rejected",
];

export function TransfersPage() {
  const { hospitals } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
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
        if (!cancelled) { setDashboard(data); setError(null); }
      } catch (err) {
        if (!cancelled && !silent) setError(err instanceof Error ? err.message : "Unable to load transfers");
      }
    }
    void load(false);
    const interval = window.setInterval(() => void load(true), 4000);
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

  const transfers = useMemo(() => {
    const all = dashboard?.transfers ?? [];
    const query = search.trim().toLowerCase();
    return all
      .filter((t) => statusFilter === "all" || t.status === statusFilter)
      .filter((t) => {
        if (!query) return true;
        const haystack = [
          t.patient_name ?? "",
          hospitalName(t.origin_hospital_id),
          hospitalName(t.destination_hospital_id),
          t.patient_condition,
          t.required_icu_type,
        ].join(" ").toLowerCase();
        return haystack.includes(query);
      })
      .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, statusFilter, search, hospitals]);

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="transfers-toolbar">
        <div className="search-field">
          <Search size={14} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by patient, hospital, or condition…"
          />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {STATUS_FILTERS.map((s) => (
            <option key={s} value={s}>{s === "all" ? "All statuses" : formatStatus(s)}</option>
          ))}
        </select>
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <h3>Transfer history</h3>
        <span className="hint">{transfers.length} shown</span>
      </div>

      <div className="row-list">
        {transfers.length ? transfers.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`row-card spine tone-${statusTone(t.urgency_class)} row-card-clickable`}
            onClick={() => void openDetail(t)}
          >
            <div className="row-main">
              <span className="row-title">{hospitalName(t.origin_hospital_id)} → {hospitalName(t.destination_hospital_id)}</span>
              <span className="row-sub">{t.patient_name ?? "Unnamed"} · {t.patient_condition} · {t.required_icu_type}</span>
            </div>
            <div className="row-figures">
              <span className={`pill tone-${statusTone(t.urgency_class)}`}>{t.urgency_class}</span>
              <span className="pill tone-offline">{formatStatus(t.status)}</span>
            </div>
          </button>
        )) : (
          <div className="card empty-state">No transfers match this filter.</div>
        )}
      </div>

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
