import { useMemo, useState } from "react";
import { AlertCircle, Bed, Building2, Loader2, Route as RouteIcon, Send, SearchX, UserRound, X } from "lucide-react";
import { apiFetch } from "../lib/api";
import {
  bloodPressureOptions,
  conditionOptions,
  consciousnessOptions,
  icuOptions,
  oxygenOptions,
  statusTone,
} from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import { ConfirmModal } from "../components/ConfirmModal";
import type { BlockingModal, Recommendation, RouteOption, TransferResponse } from "../types";

function parseVitalsText(value: string) {
  const vitals: Record<string, string> = {};
  value
    .split(/[,\n]/)
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      const [rawKey, ...rawValue] = part.split(/[:=]/);
      const key = rawKey?.trim();
      const nextValue = rawValue.join(":").trim();
      if (key && nextValue) vitals[key] = nextValue;
    });
  return Object.keys(vitals).length ? vitals : undefined;
}

function parseMedicationText(value: string) {
  return value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
}

export function TransferPlannerPage() {
  const { user, hospitals } = useAuth();
  const { t } = useLanguage();
  const isHospitalAdmin = Boolean(user?.hospital_id);

  // Step 1 — clinical picture, used to find and rank destination hospitals.
  const [originId, setOriginId] = useState(user?.hospital_id ?? hospitals[0]?.id ?? "");
  const [requiredIcu, setRequiredIcu] = useState(icuOptions[0]);
  const [conditionType, setConditionType] = useState(conditionOptions[0]);
  const [oxygen, setOxygen] = useState("low");
  const [bloodPressure, setBloodPressure] = useState("unstable");
  const [consciousness, setConsciousness] = useState("reduced");
  const [ventilatorRequired, setVentilatorRequired] = useState(true);

  // Step 2 — patient identity/packet, only needed once a destination is chosen.
  const [patientName, setPatientName] = useState("");
  const [patientIdentifier, setPatientIdentifier] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientSex, setPatientSex] = useState("unknown");
  const [patientBloodType, setPatientBloodType] = useState("");
  const [patientContact, setPatientContact] = useState("");
  const [patientAllergies, setPatientAllergies] = useState("");
  const [patientDiagnosis, setPatientDiagnosis] = useState("");
  const [patientVitals, setPatientVitals] = useState("");
  const [patientMedications, setPatientMedications] = useState("");
  const [patientIsolation, setPatientIsolation] = useState(false);

  const [loading, setLoading] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recommendationData, setRecommendationData] = useState<TransferResponse | null>(null);
  const [selectedDestinationId, setSelectedDestinationId] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteOption[]>([]);
  const [modal, setModal] = useState<BlockingModal | null>(null);
  const [pendingRecommendation, setPendingRecommendation] = useState<Recommendation | null>(null);

  const originHospital = useMemo(() => hospitals.find((h) => h.id === originId), [hospitals, originId]);
  const selectedDestination = useMemo(
    () => hospitals.find((h) => h.id === selectedDestinationId),
    [hospitals, selectedDestinationId],
  );
  const activeRoute = useMemo(
    () => routes.find((r) => r.strategy === "ml_traffic_risk_aware") ?? routes[0],
    [routes],
  );
  const icuSupportingHospitals = useMemo(
    () => hospitals.filter((h) => h.icu_types.includes(requiredIcu) && h.id !== originId),
    [hospitals, requiredIcu, originId],
  );

  function showNotice(title: string, message: string, tone: BlockingModal["tone"] = "info") {
    setModal({ title, message, tone, confirmLabel: t.planner.acknowledge });
  }

  function validatePatientPacket() {
    const missing: string[] = [];
    if (!patientName.trim()) missing.push(t.planner.patientName.toLowerCase());
    if (!patientAge.trim()) missing.push(t.planner.age.toLowerCase());
    const numericAge = Number(patientAge);
    if (patientAge.trim() && (!Number.isFinite(numericAge) || numericAge < 0 || numericAge > 130)) {
      missing.push(t.planner.age.toLowerCase());
    }
    if (!patientBloodType.trim()) missing.push(t.planner.bloodType.toLowerCase());
    if (!patientContact.trim()) missing.push(t.planner.emergencyContact.toLowerCase());
    if (missing.length) {
      showNotice(
        t.planner.patientDetailsRequiredTitle,
        t.planner.addBeforeSending.replace("{fields}", missing.join(", ")),
        "warning",
      );
      return false;
    }
    return true;
  }

  async function loadRoute(destinationId: string, urgencyClass: string) {
    setRouteLoading(true);
    setError(null);
    try {
      const response = await apiFetch("/api/routes/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_hospital_id: originId,
          destination_hospital_id: destinationId,
          urgency_class: urgencyClass,
        }),
      });
      if (!response.ok) throw new Error("Route optimization failed");
      const data: { routes: RouteOption[] } = await response.json();
      setRoutes(data.routes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected route error");
    } finally {
      setRouteLoading(false);
    }
  }

  function selectRecommendation(recommendation: Recommendation) {
    setSelectedDestinationId(recommendation.destination_hospital_id);
    void loadRoute(recommendation.destination_hospital_id, recommendationData?.urgency_class ?? "critical");
  }

  async function recommendTransfer() {
    setLoading(true);
    setError(null);
    setRoutes([]);
    setRecommendationData(null);
    setSelectedDestinationId(null);
    setPendingRecommendation(null);
    try {
      const response = await apiFetch("/api/transfers/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_hospital_id: originId,
          required_icu_type: requiredIcu,
          patient_condition: {
            condition_type: conditionType,
            oxygen_saturation_band: oxygen,
            blood_pressure_band: bloodPressure,
            consciousness_level: consciousness,
            ventilator_required: ventilatorRequired,
          },
        }),
      });
      if (!response.ok) throw new Error("Recommendation request failed");
      const data: TransferResponse = await response.json();
      setRecommendationData(data);
      const first = data.recommendations[0];
      setSelectedDestinationId(first?.destination_hospital_id ?? null);
      if (first) void loadRoute(first.destination_hospital_id, data.urgency_class);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected recommendation error");
    } finally {
      setLoading(false);
    }
  }

  async function sendTransferRequest(recommendation: Recommendation) {
    const response = await apiFetch("/api/admin/transfers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin_hospital_id: originId,
        destination_hospital_id: recommendation.destination_hospital_id,
        required_icu_type: requiredIcu,
        patient_condition: {
          condition_type: conditionType,
          oxygen_saturation_band: oxygen,
          blood_pressure_band: bloodPressure,
          consciousness_level: consciousness,
          ventilator_required: ventilatorRequired,
        },
        patient_name: patientName.trim(),
        patient_identifier_value: patientIdentifier.trim() || undefined,
        patient_age: Number(patientAge),
        patient_sex: patientSex === "unknown" ? undefined : patientSex,
        patient_blood_type: patientBloodType.trim(),
        patient_allergies: patientAllergies.trim() || undefined,
        patient_emergency_contact: patientContact.trim(),
        patient_diagnosis: patientDiagnosis.trim() || conditionType,
        patient_vitals: parseVitalsText(patientVitals),
        patient_medications: parseMedicationText(patientMedications),
        patient_isolation_required: patientIsolation,
        handover_notes: patientAllergies.trim() || undefined,
        notes: `Created from recommendation rank ${recommendation.rank}`,
      }),
    });
    if (!response.ok) {
      let detail = "Transfer request creation failed";
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
    const transfer = await response.json();
    setPendingRecommendation(null);
    showNotice(
      t.planner.requestSentTitle,
      t.planner.requestSentMessage
        .replace("{destination}", recommendation.destination_name)
        .replace("{id}", transfer.id.slice(0, 8)),
      "success",
    );
  }

  function beginPatientDetails(recommendation: Recommendation) {
    setPendingRecommendation(recommendation);
  }

  function confirmSendRequest() {
    if (!pendingRecommendation) return;
    if (!validatePatientPacket()) return;
    const recommendation = pendingRecommendation;
    setModal({
      title: t.planner.sendTransferRequestTitle,
      message: t.planner.sendConfirmMessage
        .replace("{name}", patientName.trim())
        .replace("{age}", patientAge.trim())
        .replace("{bloodType}", patientBloodType.trim())
        .replace("{origin}", originHospital?.name ?? "origin")
        .replace("{destination}", recommendation.destination_name),
      tone: "warning",
      confirmLabel: t.planner.sendRequestLabel,
      cancelLabel: t.common.cancel,
      onConfirm: () => sendTransferRequest(recommendation),
    });
  }

  const hasRun = Boolean(recommendationData);
  const noMatches = hasRun && recommendationData!.recommendations.length === 0;

  function urgencyLabel(level: string) {
    return (t.enums.urgency as Record<string, string>)[level] ?? level;
  }

  return (
    <div className="page planner-page">
      {error && <div className="page-error">{error}</div>}

      <div className="card card-pad planner-form-card">
        <h3 className="form-title"><span className="icon-chip"><Building2 size={15} /></span> {t.planner.clinicalPicture}</h3>

        <div className="form-grid">
          <label className="form-field">
            {t.planner.originHospital}
            <select
              value={originId}
              disabled={isHospitalAdmin}
              onChange={(e) => { setOriginId(e.target.value); setRecommendationData(null); setRoutes([]); }}
            >
              {hospitals.map((h) => (
                <option key={h.id} value={h.id}>{h.name} — {h.icu_types.join("/")} · {h.available_beds} {t.planner.open}</option>
              ))}
            </select>
          </label>
          <label className="form-field">
            {t.planner.requiredIcu}
            <select value={requiredIcu} onChange={(e) => setRequiredIcu(e.target.value)}>
              {icuOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="form-field">
            {t.planner.condition}
            <select value={conditionType} onChange={(e) => setConditionType(e.target.value)}>
              {conditionOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>

          <div className="form-field full" style={{ marginBottom: 6 }}>
            <span>{requiredIcu} {t.planner.availabilityAcrossNetwork}</span>
            <div className="icu-support-strip">
              {icuSupportingHospitals.length === 0 ? (
                <span className="pill tone-critical">{t.planner.noHospitalSupports} {requiredIcu}</span>
              ) : (
                icuSupportingHospitals.map((h) => (
                  <span key={h.id} className={`pill tone-${h.available_beds > 0 ? "stable" : "offline"}`}>
                    {h.name}: {h.available_beds} {t.planner.open}
                  </span>
                ))
              )}
            </div>
          </div>

          <div className="form-divider full">{t.planner.conditionDetail}</div>

          <label className="form-field">
            {t.planner.oxygen}
            <select value={oxygen} onChange={(e) => setOxygen(e.target.value)}>
              {oxygenOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="form-field">
            {t.planner.bloodPressure}
            <select value={bloodPressure} onChange={(e) => setBloodPressure(e.target.value)}>
              {bloodPressureOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="form-field">
            {t.planner.consciousness}
            <select value={consciousness} onChange={(e) => setConsciousness(e.target.value)}>
              {consciousnessOptions.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="form-check" style={{ alignSelf: "end", marginBottom: 13 }}>
            <input type="checkbox" checked={ventilatorRequired} onChange={(e) => setVentilatorRequired(e.target.checked)} />
            {t.planner.ventilatorRequired}
          </label>
        </div>

        <div className="planner-submit-row">
          <button type="button" className="btn-primary" onClick={recommendTransfer} disabled={loading || !originId}>
            {loading ? <Loader2 size={16} className="spin" /> : <RouteIcon size={16} />}
            {t.planner.findMatchingHospitals}
          </button>
        </div>
      </div>

      {hasRun && (
        <div className="card card-pad" style={{ marginTop: 20 }}>
          <div className="section-head" style={{ marginTop: 0 }}>
            <h3>{t.planner.recommendationsHeading}</h3>
            <span className={`pill tone-${statusTone(recommendationData!.urgency_class)}`}>
              {urgencyLabel(recommendationData!.urgency_class)} · {recommendationData!.urgency_score.toFixed(2)}
            </span>
          </div>

          {noMatches ? (
            <div className="empty-state" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "40px 20px" }}>
              <SearchX size={22} style={{ color: "var(--text-faint)" }} />
              <div>{t.planner.noHospitalsMatch}</div>
              <div style={{ fontSize: 12, maxWidth: 380 }}>
                {t.planner.noHospitalsMatchDetail
                  .replace("{icu}", requiredIcu)
                  .replace("{condition}", conditionType)
                  .replace("{ventilator}", ventilatorRequired ? t.planner.withVentilatorSupport : "")}
              </div>
            </div>
          ) : (
            <div className="rec-grid">
              {recommendationData!.recommendations.map((rec) => (
                <div
                  key={rec.destination_hospital_id}
                  className={`rec-tile spine tone-${rec.destination_hospital_id === selectedDestinationId ? "moderate" : "offline"}`}
                >
                  <button type="button" className="rec-select" onClick={() => selectRecommendation(rec)}>
                    <div className="rec-tile-head">
                      <span className="rec-rank">#{rec.rank}</span>
                      <span className="rec-score">{rec.score.toFixed(3)}</span>
                    </div>
                    <div className="rec-tile-name">{rec.destination_name}</div>
                    <div className="rec-tile-meta">{rec.estimated_minutes.toFixed(1)} {t.planner.minEta} · {rec.available_beds} {t.planner.bedsOpen}</div>
                  </button>
                  <button type="button" className="btn-secondary btn-block-tile" onClick={() => beginPatientDetails(rec)}>
                    <Send size={13} /> {t.planner.requestTransfer}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {selectedDestinationId && !noMatches && (
        <div className="card card-pad" style={{ marginTop: 20 }}>
          <h3 style={{ marginBottom: 14 }}>{t.planner.selectedRoutePrefix} {selectedDestination?.name}</h3>
          {routeLoading && <div className="empty-state">{t.planner.loadingRoute}</div>}
          {activeRoute && !routeLoading && (
            <div className="metric-grid" style={{ marginBottom: 0 }}>
              <div className="metric-card">
                <div className="label"><span className="icon-chip"><Bed size={15} /></span> {t.planner.availableBeds}</div>
                <div className="value">{selectedDestination?.available_beds ?? "—"}</div>
              </div>
              <div className="metric-card">
                <div className="label"><span className="icon-chip"><RouteIcon size={15} /></span> {t.planner.eta}</div>
                <div className="value">{activeRoute.estimated_minutes.toFixed(1)}<span style={{ fontSize: 13 }}> min</span></div>
              </div>
              <div className="metric-card">
                <div className="label"><span className="icon-chip tone-high"><AlertCircle size={15} /></span> {t.planner.riskScore}</div>
                <div className="value">{activeRoute.risk_score.toFixed(2)}</div>
              </div>
              <div className="metric-card">
                <div className="label">{t.planner.distance}</div>
                <div className="value">{activeRoute.distance_km.toFixed(1)}<span style={{ fontSize: 13 }}> km</span></div>
              </div>
            </div>
          )}
        </div>
      )}

      {!hasRun && !loading && (
        <div className="card empty-state" style={{ padding: "50px 20px", marginTop: 20 }}>
          {t.planner.fillClinicalPicture}
        </div>
      )}

      {pendingRecommendation && (
        <div className="drawer-backdrop" role="dialog" aria-modal="true" onClick={() => setPendingRecommendation(null)}>
          <aside className="drawer-panel" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <div>
                <h2>{t.planner.patientDetails}</h2>
                <p>{t.planner.sendingTo} {pendingRecommendation.destination_name}</p>
              </div>
              <button type="button" className="modal-close" style={{ position: "static" }} onClick={() => setPendingRecommendation(null)} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className="drawer-body">
              <p style={{ fontSize: 12.5, color: "var(--text-faint)", margin: "16px 0" }}>
                {t.planner.receivingHospitalNeeds}
              </p>
              <div className="form-grid">
                <label className="form-field full">
                  {t.planner.patientName}
                  <input value={patientName} onChange={(e) => setPatientName(e.target.value)} placeholder={t.planner.fullName} />
                </label>
                <label className="form-field">
                  {t.planner.identifier}
                  <input value={patientIdentifier} onChange={(e) => setPatientIdentifier(e.target.value)} placeholder="NIC / MRN" />
                </label>
                <label className="form-field">
                  {t.planner.age}
                  <input value={patientAge} onChange={(e) => setPatientAge(e.target.value)} inputMode="numeric" placeholder={t.planner.age} />
                </label>
                <label className="form-field">
                  {t.planner.sex}
                  <select value={patientSex} onChange={(e) => setPatientSex(e.target.value)}>
                    <option value="unknown">{t.planner.unknown}</option>
                    <option value="female">{t.planner.female}</option>
                    <option value="male">{t.planner.male}</option>
                    <option value="other">{t.planner.other}</option>
                  </select>
                </label>
                <label className="form-field">
                  {t.planner.bloodType}
                  <input value={patientBloodType} onChange={(e) => setPatientBloodType(e.target.value)} placeholder="O+, A-" />
                </label>
                <label className="form-field full">
                  {t.planner.emergencyContact}
                  <input value={patientContact} onChange={(e) => setPatientContact(e.target.value)} placeholder={t.planner.namePhone} />
                </label>
                <label className="form-field full">
                  {t.planner.workingDiagnosis}
                  <input value={patientDiagnosis} onChange={(e) => setPatientDiagnosis(e.target.value)} placeholder="Sepsis, polytrauma, STEMI..." />
                </label>
                <label className="form-field full">
                  {t.planner.allergiesAlerts}
                  <input value={patientAllergies} onChange={(e) => setPatientAllergies(e.target.value)} placeholder="Known allergies, infection risks" />
                </label>
                <label className="form-field">
                  {t.planner.vitals}
                  <input value={patientVitals} onChange={(e) => setPatientVitals(e.target.value)} placeholder="HR: 120, BP: 90/60, SpO2: 88" />
                </label>
                <label className="form-field">
                  {t.planner.medications}
                  <input value={patientMedications} onChange={(e) => setPatientMedications(e.target.value)} placeholder="Noradrenaline, ceftriaxone" />
                </label>
                <label className="form-check" style={{ alignSelf: "end", marginBottom: 13 }}>
                  <input type="checkbox" checked={patientIsolation} onChange={(e) => setPatientIsolation(e.target.checked)} />
                  {t.planner.isolationRequired}
                </label>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                <button type="button" className="btn-primary" onClick={confirmSendRequest}>
                  <UserRound size={15} /> {t.planner.sendTransferRequest}
                </button>
                <button type="button" className="btn-ghost" onClick={() => setPendingRecommendation(null)}>{t.common.cancel}</button>
              </div>
            </div>
          </aside>
        </div>
      )}

      <ConfirmModal modal={modal} onClose={() => setModal(null)} />
    </div>
  );
}
