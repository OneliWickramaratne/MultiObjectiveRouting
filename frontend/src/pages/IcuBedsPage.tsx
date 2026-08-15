import { useEffect, useMemo, useState } from "react";
import { Bed, DoorOpen, ShieldAlert, UserRound, X } from "lucide-react";
import { apiFetch } from "../lib/api";
import { icuBedStatusOptions } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import type { IcuBed } from "../types";

function parseVitalsText(value: string) {
  const vitals: Record<string, string> = {};
  value.split(/[,\n]/).map((p) => p.trim()).filter(Boolean).forEach((part) => {
    const [rawKey, ...rawValue] = part.split(/[:=]/);
    const key = rawKey?.trim();
    const nextValue = rawValue.join(":").trim();
    if (key && nextValue) vitals[key] = nextValue;
  });
  return Object.keys(vitals).length ? vitals : undefined;
}

function parseMedicationText(value: string) {
  return value.split(/[,\n]/).map((i) => i.trim()).filter(Boolean);
}

// Bed status → triage-spine tone used for the tile colors.
function bedTone(status: string) {
  if (status === "available") return "stable";
  if (status === "occupied") return "offline";
  if (status === "transfer_assigned" || status === "reserved") return "high";
  if (status === "maintenance") return "critical";
  return "offline"; // cleaning
}

const emptyForm = {
  status: "available",
  patientNo: "",
  patientName: "",
  identifier: "",
  dob: "",
  age: "",
  sex: "",
  bloodType: "",
  condition: "",
  diagnosis: "",
  vitals: "",
  medications: "",
  allergies: "",
  infectionRisk: "",
  isolation: false,
  contact: "",
  nextOfKin: "",
  address: "",
  notes: "",
};

export function IcuBedsPage() {
  const { user, hospitals } = useAuth();
  const { t } = useLanguage();
  const isSuperAdmin = user?.role === "super_admin";
  const [hospitalId, setHospitalId] = useState(user?.hospital_id ?? hospitals[0]?.id ?? "");
  const [icuTypeFilter, setIcuTypeFilter] = useState("all");
  const [beds, setBeds] = useState<IcuBed[]>([]);
  const [selectedBedId, setSelectedBedId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function statusLabel(status: string) {
    return (t.enums.bedStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }

  async function loadBeds(id: string) {
    setLoading(true);
    try {
      const response = await apiFetch(`/api/admin/hospitals/${id}/icu-beds`);
      if (!response.ok) throw new Error("ICU bed request failed");
      const data: IcuBed[] = await response.json();
      setBeds(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load ICU beds");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (hospitalId) void loadBeds(hospitalId);
    setIcuTypeFilter("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hospitalId]);

  useEffect(() => {
    const interval = window.setInterval(() => { if (hospitalId) void loadBeds(hospitalId); }, 4000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hospitalId]);

  function openBed(bed: IcuBed) {
    setSelectedBedId(bed.id);
    setForm({
      status: bed.status,
      patientNo: bed.patient?.patient_no ?? "",
      patientName: bed.patient?.patient_name ?? "",
      identifier: bed.patient?.identifier_value ?? "",
      dob: bed.patient?.date_of_birth ?? "",
      age: bed.patient?.age?.toString() ?? "",
      sex: bed.patient?.sex ?? "",
      bloodType: bed.patient?.blood_type ?? "",
      condition: bed.patient?.condition ?? "",
      diagnosis: bed.patient?.diagnosis ?? "",
      vitals: bed.patient?.vitals ? Object.entries(bed.patient.vitals).map(([k, v]) => `${k}: ${v}`).join(", ") : "",
      medications: bed.patient?.medications?.join(", ") ?? "",
      allergies: bed.patient?.allergies ?? "",
      infectionRisk: bed.patient?.infection_risk ?? "",
      isolation: bed.patient?.isolation_required ?? false,
      contact: bed.patient?.emergency_contact ?? "",
      nextOfKin: bed.patient?.next_of_kin ?? "",
      address: bed.patient?.address ?? "",
      notes: bed.patient?.notes ?? "",
    });
  }

  const selectedBed = beds.find((b) => b.id === selectedBedId) ?? null;

  async function saveBed() {
    if (!selectedBed) return;
    const hasDraft = Object.entries(form).some(([key, value]) =>
      key !== "status" ? (typeof value === "string" ? value.trim().length > 0 : value) : false,
    );
    if (hasDraft && !form.patientName.trim()) {
      setError(t.icuBeds.enterPatientNameFirst);
      return;
    }
    const parsedAge = form.age.trim() ? Number(form.age) : undefined;
    if (parsedAge !== undefined && (!Number.isFinite(parsedAge) || parsedAge < 0 || parsedAge > 130)) {
      setError(t.icuBeds.enterValidAge);
      return;
    }
    const payload = hasDraft
      ? {
          status: form.status === "available" ? "occupied" : form.status,
          patient_no: form.patientNo.trim() || `PAT-${selectedBed.bed_no}`,
          patient_name: form.patientName.trim(),
          patient_identifier_value: form.identifier.trim() || undefined,
          patient_date_of_birth: form.dob.trim() || undefined,
          patient_age: parsedAge,
          patient_sex: form.sex.trim() || undefined,
          patient_blood_type: form.bloodType.trim() || undefined,
          patient_condition: form.condition.trim() || "under observation",
          diagnosis: form.diagnosis.trim() || undefined,
          vitals: parseVitalsText(form.vitals),
          medications: parseMedicationText(form.medications),
          allergies: form.allergies.trim() || undefined,
          infection_risk: form.infectionRisk.trim() || undefined,
          isolation_required: form.isolation,
          emergency_contact: form.contact.trim() || undefined,
          next_of_kin: form.nextOfKin.trim() || undefined,
          address: form.address.trim() || undefined,
          notes: form.notes.trim() || undefined,
        }
      : { status: form.status };
    const response = await apiFetch(`/api/admin/icu-beds/${selectedBed.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setError("ICU bed update failed");
      return;
    }
    await loadBeds(hospitalId);
  }

  async function clearBed() {
    if (!selectedBed) return;
    const response = await apiFetch(`/api/admin/icu-beds/${selectedBed.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_patient: true }),
    });
    if (!response.ok) {
      setError("Patient discharge failed");
      return;
    }
    setSelectedBedId(null);
    await loadBeds(hospitalId);
  }

  const icuTypesAtHospital = useMemo(
    () => Array.from(new Set(beds.map((b) => b.icu_type))).sort(),
    [beds],
  );

  const filteredBeds = useMemo(
    () => (icuTypeFilter === "all" ? beds : beds.filter((b) => b.icu_type === icuTypeFilter)),
    [beds, icuTypeFilter],
  );

  const wardGroups = useMemo(() => {
    const groups = new Map<string, IcuBed[]>();
    filteredBeds.forEach((bed) => {
      const list = groups.get(bed.ward) ?? [];
      list.push(bed);
      groups.set(bed.ward, list);
    });
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredBeds]);

  const counts = icuBedStatusOptions.reduce<Record<string, number>>((acc, status) => {
    acc[status] = beds.filter((b) => b.status === status).length;
    return acc;
  }, {});

  return (
    <div className="page">
      {error && <div className="page-error">{error}</div>}

      <div className="metric-grid">
        {icuBedStatusOptions.slice(0, 4).map((status) => (
          <div key={status} className={`metric-card spine tone-${bedTone(status)}`}>
            <div className="label"><span className="icon-chip"><Bed size={15} /></span> {statusLabel(status)}</div>
            <div className="value">{counts[status] ?? 0}</div>
          </div>
        ))}
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <h3>{t.icuBeds.icuWardsHeading}{loading ? ` · ${t.icuBeds.loadingSuffix}` : ""}</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <select
            value={icuTypeFilter}
            onChange={(e) => setIcuTypeFilter(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 12.5 }}
          >
            <option value="all">{t.icuBeds.allIcuTypes}</option>
            {icuTypesAtHospital.map((icuType) => <option key={icuType} value={icuType}>{icuType}</option>)}
          </select>
          {isSuperAdmin && (
            <select
              value={hospitalId}
              onChange={(e) => { setHospitalId(e.target.value); setSelectedBedId(null); }}
              style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", fontSize: 12.5 }}
            >
              {hospitals.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </select>
          )}
        </div>
      </div>

      {wardGroups.length === 0 && !loading && <div className="card empty-state">{t.icuBeds.noIcuBeds}</div>}

      {wardGroups.map(([ward, wardBeds]) => (
        <div key={ward} className="ward-panel">
          <div className="ward-panel-head">
            <strong>{ward}</strong>
            <span className="ward-panel-meta">{wardBeds[0]?.icu_type} · {wardBeds.length} {t.icuBeds.beds}</span>
          </div>

          <div className="ward-room">
            <div className="ward-bed-row">
              {wardBeds.map((bed) => (
                <button
                  key={bed.id}
                  type="button"
                  className={`bed-unit tone-${bedTone(bed.status)}`}
                  onClick={() => openBed(bed)}
                  title={bed.patient?.patient_name ?? t.icuBeds.noPatient}
                >
                  {bed.patient?.isolation_required && (
                    <span className="bed-isolation-badge"><ShieldAlert size={10} /></span>
                  )}
                  <span className="bed-unit-headboard" />
                  <span className="bed-unit-pillow" />
                  <span className="bed-unit-body">
                    <span className="bed-unit-no">{bed.bed_no}</span>
                    {bed.patient ? <UserRound size={13} /> : null}
                  </span>
                  <span className="bed-unit-label">{statusLabel(bed.status)}</span>
                </button>
              ))}
            </div>

            <div className="ward-corridor">
              <span className="ward-door"><DoorOpen size={16} /> {t.icuBeds.entrance}</span>
              <span className="ward-corridor-line" />
              <span className="ward-nurse-station"><UserRound size={13} /> {t.icuBeds.nurseStation}</span>
            </div>
          </div>
        </div>
      ))}

      {selectedBed && (
        <div className="drawer-backdrop" role="dialog" aria-modal="true" onClick={() => setSelectedBedId(null)}>
          <aside className="drawer-panel" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <div>
                <h2>{t.icuBeds.bedPrefix} {selectedBed.bed_no}</h2>
                <p>{selectedBed.ward} · {selectedBed.icu_type}</p>
              </div>
              <button type="button" className="modal-close" style={{ position: "static" }} onClick={() => setSelectedBedId(null)} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className="drawer-body">
              <div className="form-grid" style={{ marginTop: 16 }}>
                <label className="form-field">
                  {t.icuBeds.status}
                  <select value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                    {icuBedStatusOptions.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                  </select>
                </label>
                <label className="form-field">
                  {t.icuBeds.patientNo}
                  <input value={form.patientNo} onChange={(e) => setForm((f) => ({ ...f, patientNo: e.target.value }))} />
                </label>
                <label className="form-field full">
                  {t.icuBeds.patientName}
                  <input value={form.patientName} onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.identifier}
                  <input value={form.identifier} onChange={(e) => setForm((f) => ({ ...f, identifier: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.dateOfBirth}
                  <input value={form.dob} onChange={(e) => setForm((f) => ({ ...f, dob: e.target.value }))} placeholder="YYYY-MM-DD" />
                </label>
                <label className="form-field">
                  {t.icuBeds.age}
                  <input value={form.age} onChange={(e) => setForm((f) => ({ ...f, age: e.target.value }))} inputMode="numeric" />
                </label>
                <label className="form-field">
                  {t.icuBeds.sex}
                  <select value={form.sex} onChange={(e) => setForm((f) => ({ ...f, sex: e.target.value }))}>
                    <option value="">{t.icuBeds.unknown}</option>
                    <option value="female">{t.icuBeds.female}</option>
                    <option value="male">{t.icuBeds.male}</option>
                    <option value="other">{t.icuBeds.other}</option>
                  </select>
                </label>
                <label className="form-field">
                  {t.icuBeds.bloodType}
                  <input value={form.bloodType} onChange={(e) => setForm((f) => ({ ...f, bloodType: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.condition}
                  <input value={form.condition} onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))} />
                </label>
                <label className="form-field full">
                  {t.icuBeds.diagnosis}
                  <input value={form.diagnosis} onChange={(e) => setForm((f) => ({ ...f, diagnosis: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.vitals}
                  <input value={form.vitals} onChange={(e) => setForm((f) => ({ ...f, vitals: e.target.value }))} placeholder="HR: 90, BP: 120/80" />
                </label>
                <label className="form-field">
                  {t.icuBeds.medications}
                  <input value={form.medications} onChange={(e) => setForm((f) => ({ ...f, medications: e.target.value }))} placeholder={t.icuBeds.commaSeparated} />
                </label>
                <label className="form-field full">
                  {t.icuBeds.allergiesAlerts}
                  <input value={form.allergies} onChange={(e) => setForm((f) => ({ ...f, allergies: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.infectionRisk}
                  <input value={form.infectionRisk} onChange={(e) => setForm((f) => ({ ...f, infectionRisk: e.target.value }))} />
                </label>
                <label className="form-check" style={{ alignSelf: "end", marginBottom: 13 }}>
                  <input type="checkbox" checked={form.isolation} onChange={(e) => setForm((f) => ({ ...f, isolation: e.target.checked }))} />
                  {t.icuBeds.isolationRequired}
                </label>
                <label className="form-field">
                  {t.icuBeds.emergencyContact}
                  <input value={form.contact} onChange={(e) => setForm((f) => ({ ...f, contact: e.target.value }))} />
                </label>
                <label className="form-field">
                  {t.icuBeds.nextOfKin}
                  <input value={form.nextOfKin} onChange={(e) => setForm((f) => ({ ...f, nextOfKin: e.target.value }))} />
                </label>
                <label className="form-field full">
                  {t.icuBeds.address}
                  <input value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
                </label>
                <label className="form-field full">
                  {t.icuBeds.notes}
                  <input value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
                </label>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                <button type="button" className="btn-primary" onClick={saveBed}>{t.icuBeds.saveBed}</button>
                <button type="button" className="btn-secondary tone-critical" onClick={clearBed}>{t.icuBeds.removePatient}</button>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
