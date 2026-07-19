import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { Activity, Ambulance, ExternalLink, Navigation } from "lucide-react";
import { apiFetch, websocketBase } from "../lib/api";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { statusTone } from "../lib/constants";
import { useAuth } from "../state/AuthContext";
import type { AmbulanceMission, AmbulanceSummary, MissionRoutePayload, TransferSummary } from "../types";

const ThreeDNavigationMap = lazy(() =>
  import("../components/ThreeDNavigationMap").then((m) => ({ default: m.ThreeDNavigationMap })),
);

function formatStatus(status: string) {
  return status.replace(/_/g, " ");
}

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

function nextMissionAction(transfer?: TransferSummary | null) {
  if (!transfer) return null;
  if (transfer.status === "ambulance_assigned") return { action: "start-pickup" as const, label: "Start pickup" };
  if (transfer.status === "ambulance_en_route_to_pickup") return { action: "arrive-pickup" as const, label: "Patient onboard" };
  if (transfer.status === "en_route_to_destination") return { action: "complete" as const, label: "Complete transfer" };
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
  const isCrew = Boolean(user?.ambulance_id);
  const [mission, setMission] = useState<AmbulanceMission | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [telemetryConnected, setTelemetryConnected] = useState(false);
  const missionStatusRef = useRef<string | null>(null);

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

  const activeMission = mission?.active_transfer ?? null;
  const activeMissionRoute = parseMissionRoute(activeMission);
  const returnRoute = parseReturnRoute(mission?.return_route_json);
  const displayedRoute = activeMissionRoute ?? returnRoute;
  const driverMode = Boolean(
    activeMission && ["ambulance_en_route_to_pickup", "en_route_to_destination"].includes(activeMission.status),
  ) || (!activeMission && Boolean(returnRoute));

  const legLabel = activeMission
    ? ["ambulance_assigned", "ambulance_en_route_to_pickup"].includes(activeMission.status)
      ? "Route to pickup hospital"
      : "Route to drop-off hospital"
    : returnRoute
      ? "Route to base hospital"
      : "";

  const nextAction = nextMissionAction(activeMission);
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
                <div className="row-sub">{formatStatus(mission.ambulance.status)}</div>
              </div>
              <span className="icon-chip"><Ambulance size={18} /></span>
            </div>
          )}

          {activeMission ? (
            <div className="card card-pad">
              <span className={`pill tone-${statusTone(activeMission.urgency_class)}`} style={{ marginBottom: 14, display: "inline-flex" }}>
                {formatStatus(activeMission.status)}
              </span>

              <div className="mission-stops">
                <div className="mission-stop">
                  <span>Pickup</span>
                  <strong>{hospitalName(activeMission.origin_hospital_id)}</strong>
                </div>
                <div className="mission-stop">
                  <span>Dropoff</span>
                  <strong>{hospitalName(activeMission.destination_hospital_id)}</strong>
                </div>
              </div>

              <div className="detail-grid" style={{ marginTop: 18 }}>
                <div><span>Urgency</span><strong>{activeMission.urgency_class}</strong></div>
                <div><span>Required ICU</span><strong>{activeMission.required_icu_type}</strong></div>
                <div><span>Route</span><strong>{legLabel}{activeMissionRoute?.estimated_minutes ? ` · ${activeMissionRoute.estimated_minutes.toFixed?.(0) ?? activeMissionRoute.estimated_minutes} min` : ""}</strong></div>
                <div><span>Road risk</span><strong>{activeMissionRoute?.risk_score?.toFixed?.(2) ?? "—"}</strong></div>
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 22 }}>
                {nextAction ? (
                  <button type="button" className="btn-primary" onClick={() => missionAction(nextAction.action)}>
                    <Navigation size={16} /> {nextAction.label}
                  </button>
                ) : (
                  <button type="button" className="btn-primary" disabled>Mission waiting</button>
                )}
                <div className={`telemetry-pill ${telemetryConnected ? "connected" : ""}`}>
                  <Activity size={14} /> {telemetryConnected ? "Live telemetry" : "Reconnecting telemetry"}
                </div>
                {mapsUrl && (
                  <a className="btn-secondary" href={mapsUrl} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                    <ExternalLink size={13} /> Open Google Maps
                  </a>
                )}
              </div>
            </div>
          ) : (
            <div className="card empty-state" style={{ padding: "60px 20px" }}>
              {returnRoute
                ? `Returning to base — ${returnRoute.estimated_minutes ?? "—"} min / ${returnRoute.distance_km ?? "—"} km. Ambulance remains available.`
                : "No active mission assigned. You'll be notified here as soon as one comes in."}
            </div>
          )}
        </div>
      )}

      {driverMode && (
        <ErrorBoundary fallbackTitle="Map failed to load">
          {mission?.ambulance && displayedRoute && (displayedRoute.polyline?.length ?? 0) >= 2 ? (
            <Suspense fallback={<div className="empty-state">Loading map…</div>}>
              <div className="driver-map-shell">
                <ThreeDNavigationMap
                  ambulance={mission.ambulance}
                  route={displayedRoute}
                  hospitals={hospitals}
                  legLabel={legLabel}
                  color="#12b981"
                />
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
                Map view isn't available right now (missing route data), but your mission controls still work below.
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
                      <ExternalLink size={13} /> Open Google Maps
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
