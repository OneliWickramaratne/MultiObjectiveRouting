import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import { TransferDetailDrawer } from "../components/TransferDetailDrawer";
import type { DashboardSummary, TransferEventSummary, TransferSummary } from "../types";

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
  const { t } = useLanguage();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedTransfer, setSelectedTransfer] = useState<TransferSummary | null>(null);
  const [transferEvents, setTransferEvents] = useState<TransferEventSummary[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  function statusLabel(status: string) {
    return (t.enums.transferStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }
  function urgencyLabel(level: string) {
    return (t.enums.urgency as Record<string, string>)[level] ?? level;
  }

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
      .filter((tr) => statusFilter === "all" || tr.status === statusFilter)
      .filter((tr) => {
        if (!query) return true;
        const haystack = [
          tr.patient_name ?? "",
          hospitalName(tr.origin_hospital_id),
          hospitalName(tr.destination_hospital_id),
          tr.patient_condition,
          tr.required_icu_type,
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
            placeholder={t.transfersPage.searchPlaceholder}
          />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {STATUS_FILTERS.map((s) => (
            <option key={s} value={s}>{s === "all" ? t.transfersPage.allStatuses : statusLabel(s)}</option>
          ))}
        </select>
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <h3>{t.transfersPage.transferHistoryHeading}</h3>
        <span className="hint">{transfers.length} {t.transfersPage.shownSuffix}</span>
      </div>

      <div className="row-list">
        {transfers.length ? transfers.map((tr) => (
          <button
            key={tr.id}
            type="button"
            className={`row-card spine tone-${statusTone(tr.urgency_class)} row-card-clickable`}
            onClick={() => void openDetail(tr)}
          >
            <div className="row-main">
              <span className="row-title">{hospitalName(tr.origin_hospital_id)} → {hospitalName(tr.destination_hospital_id)}</span>
              <span className="row-sub">{tr.patient_name ?? t.transfersPage.unnamed} · {tr.patient_condition} · {tr.required_icu_type}</span>
            </div>
            <div className="row-figures">
              <span className={`pill tone-${statusTone(tr.urgency_class)}`}>{urgencyLabel(tr.urgency_class)}</span>
              <span className="pill tone-offline">{statusLabel(tr.status)}</span>
            </div>
          </button>
        )) : (
          <div className="card empty-state">{t.transfersPage.noTransfersMatch}</div>
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
