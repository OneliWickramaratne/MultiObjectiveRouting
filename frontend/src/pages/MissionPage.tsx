import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Activity, Ambulance, ExternalLink, Map as MapIcon, Navigation } from "lucide-react";
import { apiFetch, websocketBase } from "../lib/api";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { TwoDNavigationMap } from "../components/TwoDNavigationMap";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import { useLanguage } from "../i18n/LanguageContext";
import type { AmbulanceMission, AmbulanceSummary, MissionRoutePayload, TransferSummary } from "../types";
import type { TranslationKeys } from "../i18n/translations";

const ThreeDNavigationMap = lazy(() =>
  import("../components/ThreeDNavigationMap").then((m) => ({ default: m.ThreeDNavigationMap })),
);

function parseMissionRoute(transfer?: TransferSummary | null): MissionRoutePayload | null {
  if (!transfer?.route_payload_json) return null;
  try {
    const parsed = JSON.parse(transfer.route_payload_json) as {
      pickup_route?: MissionRoutePayload;
      destination_route?: MissionRoutePayload;
      mission_route?: MissionRoutePayload;
    };
    if (["ambulance_assigned", "ambulance_en_route_to_pickup"].includes(transfer.status)) {
      return parsed.pickup_route ?? parsed.mission_route ?? null;
    }
    return parsed.destination_route ?? parsed.mission_route ?? null;
  } catch {
    return null;
  }
}

function parseReturnRoute(value?: string | null): MissionRoutePayload | null {
  if (!value) return null;
  try {
    return JSON.parse(value) as MissionRoutePayload;
  } catch {
    return null;
  }
}

function nextMissionAction(transfer: TransferSummary | null | undefined, t: TranslationKeys) {
  if (!transfer) return null;
  if (transfer.status === "ambulance_assigned") return { action: "start-pickup" as const, label: t.mission.startPickup };
  if (transfer.status === "ambulance_en_route_to_pickup") return { action: "arrive-pickup" as const, label: t.mission.patientOnboard };
  if (transfer.status === "en_route_to_destination") return { action: "complete" as const, label: t.mission.completeTransfer };
  return null;
}

function googleMapsUrl(transfer?: TransferSummary | null) {
  if (!transfer) return null;
  const { pickup_latitude, pickup_longitude, dropoff_latitude, dropoff_longitude } = transfer;
  if (pickup_latitude == null || pickup_longitude == null || dropoff_latitude == null || dropoff_longitude == null) {
    return null;
  }
  return `https://www.google.com/maps/dir/?api=1&origin=${pickup_latitude},${pickup_longitude}&destination=${dropoff_latitude},${dropoff_longitude}&travelmode=driving`;
}

export function MissionPage() {
  const { hospitals, user } = useAuth();
  const { t } = useLanguage();
  const isCrew = Boolean(user?.ambulance_id);
  const [mission, setMission] = useState<AmbulanceMission | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [telemetryConnected, setTelemetryConnected] = useState(false);
  const [mapMode, setMapMode] = useState<"3d" | "2d">("3d");
  const missionStatusRef = useRef<string | null>(null);

  function statusLabel(status: string) {
    return (t.enums.transferStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }
  function ambulanceStatusLabel(status: string) {
    return (t.enums.ambulanceStatus as Record<string, string>)[status] ?? status.split("_").join(" ");
  }

  async function loadMission(silent = false) {
    if (!isCrew) return;
    try {
      const response = await apiFetch("/api/ambulance/mission");
      if (!response.ok) throw new Error("Mission request failed");
      const data: AmbulanceMission = await response.json();
      setMission(data);
      setError(null);
    } catch (err) {
      if (!silent) setError(err instanceof Error ? err.message : "Unable to load mission");
    }
  }

  useEffect(() => {
    void loadMission(false);
    const interval = window.setInterval(() => void loadMission(true), 4000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    missionStatusRef.current = mission?.active_transfer?.status ?? null;
  }, [mission?.active_transfer?.status]);

  // Live ambulance position via WebSocket telemetry, with polling as the fallback.
  useEffect(() => {
    if (!isCrew) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    async function connect() {
      try {
        const ticketResponse = await apiFetch("/api/auth/event-stream-ticket", { method: "POST" });
        if (!ticketResponse.ok || disposed) return;
        const { ticket } = await ticketResponse.json();
        socket = new WebSocket(`${websocketBase()}/api/ambulance/telemetry?ticket=${encodeURIComponent(ticket)}`);
        socket.onopen = () => setTelemetryConnected(true);
        socket.onmessage = (event) => {
          const payload = JSON.parse(event.data) as {
            kind: string;
            ambulance: AmbulanceSummary;
            active_transfer_status: string | null;
          };
          if (payload.kind !== "ambulance_telemetry") return;
          setMission((current) => (current ? { ...current, ambulance: payload.ambulance } : current));
          if (payload.active_transfer_status && payload.active_transfer_status !== missionStatusRef.current) {
            void loadMission(true);
          }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = () => {
          setTelemetryConnected(false);
          if (!disposed) reconnectTimer = window.setTimeout(connect, 1500);
        };
      } catch {
        setTelemetryConnected(false);
        if (!disposed) reconnectTimer = window.setTimeout(connect, 2000);
      }
    }
    void connect();
    return () => {
      disposed = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      socket?.close();
      setTelemetryConnected(false);
    };
  }, []);

  async function missionAction(action: "start-pickup" | "arrive-pickup" | "complete") {
    const transferId = mission?.active_transfer?.id;
    if (!transferId) return;
    const response = await apiFetch(`/api/ambulance/mission/${transferId}/${action}`, { method: "POST" });
    if (!response.ok) {
      setError("Mission update failed");
      return;
    }
    setMission(await response.json());
  }

  function hospitalName(id: string) {
    return hospitals.find((h) => h.id === id)?.name ?? `Hospital ${id}`;
  }

  function urgencyLabel(level: string) {
    return (t.enums.urgency as Record<string, string>)[level] ?? level;
  }

  const activeMission = mission?.active_transfer ?? null;
  const activeMissionRoute = parseMissionRoute(activeMission);
  const returnRoute = parseReturnRoute(mission?.return_route_json);
  const displayedRoute = activeMissionRoute ?? returnRoute;
  const driverMode = Boolean(
    activeMission && ["ambulance_en_route_to_pickup", "en_route_to_destination"].includes(activeMission.status),
  ) || (!activeMission && Boolean(returnRoute));

  const legLabel = activeMission
    ? ["ambulance_assigned", "ambulance_en_route_to_pickup"].includes(activeMission.status)
      ? t.mission.routeToPickup
      : t.mission.routeToDropoff
    : returnRoute
      ? t.mission.routeToBase
      : "";

  const nextAction = nextMissionAction(activeMission, t);
  const mapsUrl = googleMapsUrl(activeMission);

  return (
    <div className={driverMode ? "mission-page driver" : "mission-page"}>
      {!driverMode && (
        <div className="page" style={{ maxWidth: 780 }}>
          {error && <div className="page-error">{error}</div>}

          {mission?.ambulance && (
            <div className="card card-pad" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div>
                <div className="row-title" style={{ fontSize: 15 }}>{mission.ambulance.call_sign}</div>
                <div className="row-sub">{ambulanceStatusLabel(mission.ambulance.status)}</div>
              </div>
              <span className="icon-chip"><Ambulance size={18} /></span>
            </div>
          )}

          {activeMission ? (
            <div className="card card-pad">
              <span className={`pill tone-${statusTone(activeMission.urgency_class)}`} style={{ marginBottom: 14, display: "inline-flex" }}>
                {statusLabel(activeMission.status)}
              </span>

              <div className="mission-stops">
                <div className="mission-stop">
                  <span>{t.mission.pickup}</span>
                  <strong>{hospitalName(activeMission.origin_hospital_id)}</strong>
                </div>
                <div className="mission-stop">
                  <span>{t.mission.dropoff}</span>
                  <strong>{hospitalName(activeMission.destination_hospital_id)}</strong>
                </div>
              </div>

              <div className="detail-grid" style={{ marginTop: 18 }}>
                <div><span>{t.mission.urgency}</span><strong>{urgencyLabel(activeMission.urgency_class)}</strong></div>
                <div><span>{t.mission.requiredIcu}</span><strong>{activeMission.required_icu_type}</strong></div>
                <div><span>{t.mission.route}</span><strong>{legLabel}{activeMissionRoute?.estimated_minutes ? ` · ${activeMissionRoute.estimated_minutes.toFixed?.(0) ?? activeMissionRoute.estimated_minutes} min` : ""}</strong></div>
                <div><span>{t.mission.roadRisk}</span><strong>{activeMissionRoute?.risk_score?.toFixed?.(2) ?? "—"}</strong></div>
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 22 }}>
                {nextAction ? (
                  <button type="button" className="btn-primary" onClick={() => missionAction(nextAction.action)}>
                    <Navigation size={16} /> {nextAction.label}
                  </button>
                ) : (
                  <button type="button" className="btn-primary" disabled>{t.mission.missionWaiting}</button>
                )}
                <div className={`telemetry-pill ${telemetryConnected ? "connected" : ""}`}>
                  <Activity size={14} /> {telemetryConnected ? t.mission.liveTelemetry : t.mission.reconnectingTelemetry}
                </div>
                {mapsUrl && (
                  <a className="btn-secondary" href={mapsUrl} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                    <ExternalLink size={13} /> {t.mission.openGoogleMaps}
                  </a>
                )}
              </div>
            </div>
          ) : (
            <div className="card empty-state" style={{ padding: "60px 20px" }}>
              {returnRoute
                ? t.mission.returningToBase
                    .replace("{minutes}", String(returnRoute.estimated_minutes ?? "—"))
                    .replace("{distance}", String(returnRoute.distance_km ?? "—"))
                : t.mission.noActiveMission}
            </div>
          )}
        </div>
      )}

      {driverMode && (
        <ErrorBoundary key={mapMode} fallbackTitle={t.mission.mapFailedToLoad}>
          {mission?.ambulance && displayedRoute && (displayedRoute.polyline?.length ?? 0) >= 2 ? (
            <Suspense fallback={<div className="empty-state">{t.mission.loadingMap}</div>}>
              <div className="driver-map-shell" key={mapMode}>
                {mapMode === "3d" ? (
                  <ThreeDNavigationMap
                    ambulance={mission.ambulance}
                    route={displayedRoute}
                    hospitals={hospitals}
                    legLabel={legLabel}
                    color="#12b981"
                  />
                ) : (
                  <TwoDNavigationMap
                    ambulance={mission.ambulance}
                    route={displayedRoute}
                    hospitals={hospitals}
                    legLabel={legLabel}
                    color="#12b981"
                  />
                )}
                <button
                  type="button"
                  className="map-mode-toggle"
                  onClick={() => setMapMode((mode) => (mode === "3d" ? "2d" : "3d"))}
                  title={mapMode === "3d" ? t.mission.switchTo2D : t.mission.switchTo3D}
                >
                  <MapIcon size={15} /> {mapMode === "3d" ? "2D" : "3D"}
                </button>
                <div className="driver-overlay">
                  <div className="driver-overlay-card">
                    <strong>{legLabel}</strong>
                    <span>{displayedRoute.estimated_minutes ?? "—"} min · {displayedRoute.distance_km ?? "—"} km</span>
                  </div>
                  {activeMission && (
                    <div className="driver-overlay-actions">
                      {nextAction ? (
                        <button type="button" className="btn-primary" onClick={() => missionAction(nextAction.action)}>
                          <Navigation size={16} /> {nextAction.label}
                        </button>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            </Suspense>
          ) : (
            // The map couldn't be shown (missing route/vehicle data) — never leave
            // the crew with a blank screen; keep the mission controls usable.
            <div className="page" style={{ maxWidth: 780 }}>
              <div className="card empty-state" style={{ padding: "40px 20px", marginBottom: 16 }}>
                {t.mission.mapUnavailable}
              </div>
              {activeMission && (
                <div className="card card-pad" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <strong style={{ display: "block", fontSize: 14 }}>{legLabel}</strong>
                    <span className="row-sub">{hospitalName(activeMission.origin_hospital_id)} → {hospitalName(activeMission.destination_hospital_id)}</span>
                  </div>
                  {nextAction ? (
                    <button type="button" className="btn-primary" onClick={() => missionAction(nextAction.action)}>
                      <Navigation size={16} /> {nextAction.label}
                    </button>
                  ) : null}
                  {mapsUrl && (
                    <a className="btn-secondary" href={mapsUrl} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                      <ExternalLink size={13} /> {t.mission.openGoogleMaps}
                    </a>
                  )}
                </div>
              )}
            </div>
          )}
        </ErrorBoundary>
      )}
    </div>
  );
}
