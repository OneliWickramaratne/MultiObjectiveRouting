import { useEffect, useMemo, useState } from "react";
import { Marker, MapContainer, Polyline, Popup, TileLayer } from "react-leaflet";
import { divIcon } from "leaflet";
import { Ambulance, Building2 } from "lucide-react";
import { apiFetch } from "../lib/api";
import { statusTone } from "../lib/constants";
import { useLanguage } from "../i18n/LanguageContext";
import type { AmbulanceSummary, CapacityForecastSummary, DashboardSummary, Hospital, TransferSummary } from "../types";

const TONE_HEX: Record<string, string> = {
  critical: "#d6453d",
  high: "#dc8a1f",
  moderate: "#279467",
  stable: "#279467",
  offline: "#8497a0",
};

const ACTIVE_MISSION_STATUSES = ["ambulance_assigned", "ambulance_en_route_to_pickup", "en_route_to_destination"];

function missionRoutePolyline(transfer: TransferSummary): [number, number][] | null {
  if (!transfer.route_payload_json) return null;
  try {
    const parsed = JSON.parse(transfer.route_payload_json) as {
      pickup_route?: { polyline?: [number, number][] };
      destination_route?: { polyline?: [number, number][] };
      mission_route?: { polyline?: [number, number][] };
    };
    const leg = ["ambulance_assigned", "ambulance_en_route_to_pickup"].includes(transfer.status)
      ? parsed.pickup_route ?? parsed.mission_route
      : parsed.destination_route ?? parsed.mission_route;
    return leg?.polyline?.filter((p) => Number.isFinite(p?.[0]) && Number.isFinite(p?.[1])) ?? null;
  } catch {
    return null;
  }
}

function returnRoutePolyline(ambulance: AmbulanceSummary): [number, number][] | null {
  if (!ambulance.return_route_json) return null;
  try {
    const parsed = JSON.parse(ambulance.return_route_json) as { polyline?: [number, number][] };
    const points = parsed.polyline?.filter((p) => Number.isFinite(p?.[0]) && Number.isFinite(p?.[1])) ?? null;
    return points && points.length >= 2 ? points : null;
  } catch {
    return null;
  }
}
function hospitalMarkerHtml(color: string, label: string) {
  return `<div style="
    width: 30px; height: 30px; border-radius: 8px;
    background: ${color}; color: #fff; display: flex; align-items: center;
    justify-content: center; font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; font-weight: 700; box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    border: 2px solid #fff;
  ">${label}</div>`;
}

function ambulanceMarkerHtml(color: string, transporting: boolean) {
  const badge = transporting
    ? `<div style="position:absolute; top:-4px; right:-4px; width:9px; height:9px; border-radius:50%; background:#fff; border:2px solid ${color};"></div>`
    : "";
  return `<div style="
    position: relative;
    width: 22px; height: 22px; border-radius: 50%;
    background: ${color}; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 3px 8px rgba(0,0,0,0.35); border: 2px solid #fff;
  "><div style="width:8px;height:8px;background:#fff;border-radius:2px;"></div>${badge}</div>`;
}

export function NetworkMapPage() {
  const { t } = useLanguage();
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [forecast, setForecast] = useState<CapacityForecastSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  function pressureLabel(level: string) {
    return (t.enums.pressure as Record<string, string>)[level] ?? level;
  }
  function ambulanceStatusLabel(status: string) {
    return (t.enums.ambulanceStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }

  useEffect(() => {
    let cancelled = false;
    async function load(silent: boolean) {
      try {
        const [dashRes, forecastRes] = await Promise.all([
          apiFetch("/api/admin/dashboard"),
          apiFetch("/api/admin/capacity/forecast"),
        ]);
        if (!cancelled && dashRes.ok) setDashboard(await dashRes.json());
        if (!cancelled && forecastRes.ok) setForecast(await forecastRes.json());
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled && !silent) setError(err instanceof Error ? err.message : "Unable to load network map data");
      }
    }
    void load(false);
    const interval = window.setInterval(() => void load(true), 4000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, []);

  const hospitals = dashboard?.hospitals ?? [];
  const ambulances = dashboard?.ambulances ?? [];
  const activeMissions = useMemo(
    () =>
      (dashboard?.transfers ?? [])
        .filter((t) => ACTIVE_MISSION_STATUSES.includes(t.status) && t.ambulance_id)
        .map((t) => ({ transfer: t, polyline: missionRoutePolyline(t) }))
        .filter((m): m is { transfer: TransferSummary; polyline: [number, number][] } => Boolean(m.polyline && m.polyline.length >= 2)),
    [dashboard],
  );
  const returnTrips = useMemo(
    () =>
      ambulances
        .map((a) => ({ ambulance: a, polyline: returnRoutePolyline(a) }))
        .filter((r): r is { ambulance: AmbulanceSummary; polyline: [number, number][] } => Boolean(r.polyline)),
    [ambulances],
  );

  const pressureByHospital = useMemo(() => {
    const map = new Map<string, string>();
    (forecast?.hospitals ?? []).forEach((h) => {
      if (h.points[0]) map.set(h.hospital_id, h.points[0].pressure_level);
    });
    return map;
  }, [forecast]);

  function hospitalIcon(hospital: Hospital) {
    const tone = statusTone(pressureByHospital.get(hospital.id) ?? "stable");
    const initials = hospital.name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).map((w) => w[0]).slice(0, 3).join("") || hospital.name.slice(0, 2).toUpperCase();
    return divIcon({
      html: hospitalMarkerHtml(TONE_HEX[tone] ?? TONE_HEX.stable, initials),
      className: "",
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  function ambulanceIcon(ambulance: AmbulanceSummary) {
    const tone = ambulance.status === "available" ? "stable"
      : ambulance.status === "offline" ? "critical"
      : ["assigned", "en_route", "transporting"].includes(ambulance.status) ? "high"
      : "offline";
    return divIcon({
      html: ambulanceMarkerHtml(TONE_HEX[tone], ambulance.status === "transporting"),
      className: "",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
  }

  const center: [number, number] = hospitals.length
    ? [
        hospitals.reduce((s, h) => s + h.latitude, 0) / hospitals.length,
        hospitals.reduce((s, h) => s + h.longitude, 0) / hospitals.length,
      ]
    : [6.9147, 79.8728];

  return (
    <div className="page network-map-page">
      {error && <div className="page-error">{error}</div>}

      <div className="map-legend-bar">
        <span className="legend-item"><span className="icon-chip"><Building2 size={13} /></span> {t.networkMap.hospitalsColoredByPressure}</span>
        <span className="legend-item"><span className="icon-chip"><Ambulance size={13} /></span> {t.networkMap.ambulancesColoredByStatus}</span>
        <span className="legend-dot" style={{ background: TONE_HEX.stable }} /> {t.enums.pressure.stable}
        <span className="legend-dot" style={{ background: TONE_HEX.high }} /> {t.enums.pressure.high}
        <span className="legend-dot" style={{ background: TONE_HEX.critical }} /> {t.enums.pressure.critical}
        <span className="legend-item">{t.networkMap.legendRoutes}</span>
      </div>

      <div className="network-map-shell">
        <MapContainer center={center} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap &copy; CARTO'
          />
          {returnTrips.map(({ ambulance, polyline }) => (
            <Polyline
              key={`return-${ambulance.id}`}
              positions={polyline}
              pathOptions={{ color: TONE_HEX.offline, weight: 2, opacity: 0.55, dashArray: "1 7" }}
            />
          ))}
          {activeMissions.map(({ transfer, polyline }) => (
            <Polyline
              key={transfer.id}
              positions={polyline}
              pathOptions={{
                color: TONE_HEX[statusTone(transfer.urgency_class)],
                weight: 3,
                opacity: 0.75,
                dashArray: transfer.status === "en_route_to_destination" ? undefined : "2 8",
              }}
            />
          ))}
          {hospitals.map((hospital) => (
            <Marker key={hospital.id} position={[hospital.latitude, hospital.longitude]} icon={hospitalIcon(hospital)}>
              <Popup>
                <strong>{hospital.name}</strong>
                <br />
                {hospital.icu_types.join(", ")}
                <br />
                {hospital.available_beds} / {hospital.total_beds} {t.capacity.bedsOpen}
                <br />
                {t.networkMap.pressure} {pressureLabel(pressureByHospital.get(hospital.id) ?? "stable")}
              </Popup>
            </Marker>
          ))}
          {ambulances.map((ambulance) => (
            <Marker key={ambulance.id} position={[ambulance.latitude, ambulance.longitude]} icon={ambulanceIcon(ambulance)}>
              <Popup>
                <strong>{ambulance.call_sign}</strong>
                <br />
                {ambulanceStatusLabel(ambulance.status)}
                <br />
                {ambulance.speed_kph ? `${Math.round(ambulance.speed_kph)} km/h` : t.networkMap.stopped}
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
