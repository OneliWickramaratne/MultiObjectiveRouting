import { useEffect, useRef } from "react";
import { MapContainer, Marker, Polyline, TileLayer, useMap } from "react-leaflet";
import { divIcon, LatLngBounds } from "leaflet";
import type { AmbulanceSummary, Hospital, MissionRoutePayload } from "../types";

type TwoDNavigationMapProps = {
  ambulance?: AmbulanceSummary | null;
  route?: MissionRoutePayload | null;
  hospitals: Hospital[];
  legLabel: string;
  color: string;
};

function ambulanceMarkerHtml(color: string) {
  return `<div style="
    width: 26px; height: 26px; border-radius: 50%;
    background: ${color}; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 3px 10px rgba(0,0,0,0.4); border: 3px solid #fff;
  "><div style="width:9px;height:9px;background:#fff;border-radius:2px;"></div></div>`;
}

function endpointMarkerHtml(color: string, label: string) {
  return `<div style="
    width: 22px; height: 22px; border-radius: 50%;
    background: #fff; color: ${color}; display: flex; align-items: center; justify-content: center;
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 800;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3); border: 2px solid ${color};
  ">${label}</div>`;
}

// Fits the map to the route bounds once when the route genuinely changes
// (by leg + endpoint, not on every poll) — mirrors the fix already applied
// to the 3D driver view, so this map doesn't jitter every few seconds while
// a return-to-base route is continuously recomputed from the current
// position.
function FitRouteBounds({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap();
  const lastFitRef = useRef<string | null>(null);

  useEffect(() => {
    if (points.length < 2) return;
    if (lastFitRef.current === fitKey) return;
    const bounds = points.reduce(
      (current, point) => current.extend(point),
      new LatLngBounds(points[0], points[0]),
    );
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16 });
    lastFitRef.current = fitKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map]);

  return null;
}

export function TwoDNavigationMap({ ambulance, route, legLabel, color }: TwoDNavigationMapProps) {
  const points = (route?.polyline ?? []).filter(
    (p) => Number.isFinite(p?.[0]) && Number.isFinite(p?.[1]),
  );

  const fallbackCenter: [number, number] = ambulance && Number.isFinite(ambulance.latitude)
    ? [ambulance.latitude, ambulance.longitude]
    : [6.9147, 79.8728];
  const initialCenter = points[0] ?? fallbackCenter;
  const start = points[0];
  const end = points.at(-1);
  const fitKey = `${legLabel}-${end?.join(",") ?? ""}`;

  const ambulanceIcon = divIcon({
    html: ambulanceMarkerHtml(color),
    className: "",
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
  const startIcon = divIcon({
    html: endpointMarkerHtml(color, "A"),
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
  const endIcon = divIcon({
    html: endpointMarkerHtml(color, "B"),
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });

  return (
    <MapContainer center={initialCenter} zoom={13} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap &copy; CARTO'
      />
      {points.length >= 2 && <FitRouteBounds points={points} fitKey={fitKey} />}
      {points.length >= 2 && (
        <Polyline positions={points} pathOptions={{ color, weight: 5, opacity: 0.85 }} />
      )}
      {start && <Marker position={start} icon={startIcon} />}
      {end && <Marker position={end} icon={endIcon} />}
      {ambulance && Number.isFinite(ambulance.latitude) && Number.isFinite(ambulance.longitude) && (
        <Marker position={[ambulance.latitude, ambulance.longitude]} icon={ambulanceIcon} />
      )}
    </MapContainer>
  );
}
