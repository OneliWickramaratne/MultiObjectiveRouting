import { Compass, LocateFixed, Map as MapIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { LngLatBounds, Marker, type Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type AmbulanceSummary = {
  id: string;
  call_sign: string;
  base_hospital_id: string | null;
  status: string;
  latitude: number;
  longitude: number;
  heading_degrees?: number;
  speed_kph?: number;
  route_progress_m?: number;
  navigation_leg?: string | null;
  telemetry_updated_at?: string | null;
};

type MissionRoutePayload = {
  distance_km?: number;
  estimated_minutes?: number;
  risk_score?: number | null;
  route_nodes?: string[];
  polyline?: [number, number][];
};

type Hospital = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
};

type ThreeDNavigationMapProps = {
  ambulance?: AmbulanceSummary | null;
  route?: MissionRoutePayload | null;
  hospitals: Hospital[];
  legLabel: string;
  color: string;
};

type RouteTrack = {
  points: [number, number][];
  cumulative: number[];
  totalMeters: number;
};

type MotionFrame = {
  routeKey: string;
  displayedProgress: number;
  startProgress: number;
  targetProgress: number;
  transitionStartedAt: number;
  transitionDurationMs: number;
  authoritativeReceivedAt: number;
  speedMps: number;
  heading: number;
  cameraBearing: number;
  lastFrameAt: number;
  lastRoutePaintAt: number;
};

const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const NAVIGATION_ROUTE_COLOR = "#1677ff";
const EARTH_RADIUS_M = 6_371_000;

function haversineMeters(first: [number, number], second: [number, number]) {
  const lat1 = first[0] * Math.PI / 180;
  const lat2 = second[0] * Math.PI / 180;
  const deltaLat = (second[0] - first[0]) * Math.PI / 180;
  const deltaLng = (second[1] - first[1]) * Math.PI / 180;
  const value = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) ** 2;
  return EARTH_RADIUS_M * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(Math.max(1 - value, 0)));
}

function bearing(from: [number, number], to: [number, number]) {
  const fromLat = from[0] * Math.PI / 180;
  const toLat = to[0] * Math.PI / 180;
  const deltaLng = (to[1] - from[1]) * Math.PI / 180;
  const y = Math.sin(deltaLng) * Math.cos(toLat);
  const x = Math.cos(fromLat) * Math.sin(toLat) - Math.sin(fromLat) * Math.cos(toLat) * Math.cos(deltaLng);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function interpolateAngle(current: number, target: number, ratio: number) {
  const delta = ((target - current + 540) % 360) - 180;
  return (current + delta * ratio + 360) % 360;
}

function isFiniteCoordinate(point: [number, number] | null | undefined): point is [number, number] {
  return (
    Array.isArray(point) &&
    point.length === 2 &&
    Number.isFinite(point[0]) &&
    Number.isFinite(point[1])
  );
}

function buildTrack(polyline: [number, number][]): RouteTrack | null {
  // Route data occasionally contains a null/NaN coordinate pair (e.g. from a
  // fallback route built while a hospital or ambulance position was
  // momentarily unset). A single bad point here crashes MapLibre's bounds
  // math and blanks the entire map, so filter defensively before using it.
  const validPolyline = polyline.filter(isFiniteCoordinate);
  const points: [number, number][] = [];
  for (const point of validPolyline) {
    if (points.length && haversineMeters(points[points.length - 1], point) < 0.25) {
      continue;
    }
    points.push(point);
  }
  if (points.length < 2) {
    return null;
  }
  const cumulative = [0];
  for (let index = 1; index < points.length; index += 1) {
    cumulative.push(cumulative[index - 1] + haversineMeters(points[index - 1], points[index]));
  }
  return { points, cumulative, totalMeters: cumulative[cumulative.length - 1] };
}

function segmentAtProgress(track: RouteTrack, progress: number) {
  const bounded = Math.max(0, Math.min(progress, track.totalMeters));
  let low = 0;
  let high = track.cumulative.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (track.cumulative[middle] < bounded) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return Math.max(0, Math.min(low - 1, track.points.length - 2));
}

function positionAtProgress(track: RouteTrack, progress: number): [number, number] {
  const bounded = Math.max(0, Math.min(progress, track.totalMeters));
  const index = segmentAtProgress(track, bounded);
  const segmentStart = track.cumulative[index];
  const segmentLength = Math.max(track.cumulative[index + 1] - segmentStart, 0.001);
  const ratio = Math.max(0, Math.min((bounded - segmentStart) / segmentLength, 1));
  return [
    track.points[index][0] + (track.points[index + 1][0] - track.points[index][0]) * ratio,
    track.points[index][1] + (track.points[index + 1][1] - track.points[index][1]) * ratio,
  ];
}

function headingAtProgress(track: RouteTrack, progress: number) {
  let start = positionAtProgress(track, progress);
  const end = positionAtProgress(track, Math.min(progress + 26, track.totalMeters));
  if (haversineMeters(start, end) < 0.5) {
    start = positionAtProgress(track, Math.max(0, progress - 26));
  }
  return bearing(start, end);
}

function projectProgress(track: RouteTrack, latitude: number, longitude: number, minimumProgress = 0) {
  const metersPerDegreeLat = Math.PI * EARTH_RADIUS_M / 180;
  const metersPerDegreeLng = metersPerDegreeLat * Math.max(Math.cos(latitude * Math.PI / 180), 0.01);
  let bestProgress = minimumProgress;
  let bestOffset = Number.POSITIVE_INFINITY;
  for (let index = 0; index < track.points.length - 1; index += 1) {
    if (track.cumulative[index + 1] + 35 < minimumProgress) {
      continue;
    }
    const start = track.points[index];
    const end = track.points[index + 1];
    const startX = (start[1] - longitude) * metersPerDegreeLng;
    const startY = (start[0] - latitude) * metersPerDegreeLat;
    const endX = (end[1] - longitude) * metersPerDegreeLng;
    const endY = (end[0] - latitude) * metersPerDegreeLat;
    const deltaX = endX - startX;
    const deltaY = endY - startY;
    const lengthSquared = deltaX * deltaX + deltaY * deltaY;
    let ratio = Math.max(0, Math.min(
      lengthSquared < 0.001 ? 0 : -(startX * deltaX + startY * deltaY) / lengthSquared,
      1,
    ));
    const segmentLength = Math.max(track.cumulative[index + 1] - track.cumulative[index], 0.001);
    const minimumRatio = Math.max(
      0,
      Math.min((minimumProgress - track.cumulative[index]) / segmentLength, 1),
    );
    ratio = Math.max(ratio, minimumRatio);
    const offset = Math.hypot(startX + deltaX * ratio, startY + deltaY * ratio);
    if (offset < bestOffset) {
      bestOffset = offset;
      bestProgress = track.cumulative[index]
        + (track.cumulative[index + 1] - track.cumulative[index]) * ratio;
    }
  }
  return { progress: Math.max(bestProgress, minimumProgress), offset: bestOffset };
}

function routeCoordinates(track: RouteTrack, progress: number, traveled: boolean) {
  const index = segmentAtProgress(track, progress);
  const current = positionAtProgress(track, progress);
  const selected = traveled
    ? [...track.points.slice(0, index + 1), current]
    : [current, ...track.points.slice(index + 1)];
  const coordinates = selected.map(([latitude, longitude]) => [longitude, latitude]);
  if (coordinates.length === 1) {
    coordinates.push([...coordinates[0]]);
  }
  return coordinates;
}

function routeFeature(coordinates: number[][]) {
  return {
    type: "FeatureCollection" as const,
    features: [{
      type: "Feature" as const,
      properties: {},
      geometry: { type: "LineString" as const, coordinates },
    }],
  };
}

function ambulanceElement(color: string, label: string) {
  const element = document.createElement("div");
  element.className = "maplibre-ambulance-marker";
  element.style.setProperty("--vehicle-color", color);
  const visual = document.createElement("span");
  visual.className = "vehicle-visual";
  const body = document.createElement("span");
  body.className = "vehicle-body";
  const cab = document.createElement("span");
  cab.className = "vehicle-cab";
  const cross = document.createElement("span");
  cross.className = "vehicle-cross";
  cross.textContent = "+";
  const badge = document.createElement("small");
  badge.textContent = label;
  visual.append(body, cab, cross);
  element.append(visual, badge);
  return element;
}

function stopElement(type: "pickup" | "dropoff" | "base") {
  const element = document.createElement("div");
  element.className = `maplibre-stop-marker ${type}`;
  element.textContent = type === "pickup" ? "P" : type === "dropoff" ? "D" : "B";
  return element;
}

export function ThreeDNavigationMap({ ambulance, route, hospitals, legLabel, color }: ThreeDNavigationMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const ambulanceMarkerRef = useRef<Marker | null>(null);
  const ambulanceElementRef = useRef<HTMLElement | null>(null);
  const stopMarkersRef = useRef<Marker[]>([]);
  const frameRef = useRef<number | null>(null);
  const followingRef = useRef(true);
  const northUpRef = useRef(false);
  const routeTrackRef = useRef<RouteTrack | null>(null);
  const overviewUntilRef = useRef(0);
  const motionRef = useRef<MotionFrame | null>(null);
  const initialCenterRef = useRef<[number, number]>(
    ambulance && Number.isFinite(ambulance.longitude) && Number.isFinite(ambulance.latitude)
      ? [ambulance.longitude, ambulance.latitude]
      : [79.871, 6.906],
  );
  const [isFollowing, setIsFollowing] = useState(true);
  const [northUp, setNorthUp] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const routeKey = useMemo(
    () => {
      const points = route?.polyline ?? [];
      return `${points.length}-${points[0]?.join(",") ?? ""}-${points.at(-1)?.join(",") ?? ""}-${legLabel}`;
    },
    [legLabel, route?.polyline],
  );
  const track = useMemo(() => buildTrack(route?.polyline ?? []), [routeKey]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: initialCenterRef.current,
      zoom: 17.7,
      pitch: 62,
      bearing: -22,
      maxPitch: 72,
      attributionControl: false,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    map.on("error", (event) => {
      // MapLibre reports tile/style/network failures via this event rather
      // than throwing — without this, a failed basemap fetch just leaves a
      // blank canvas with no indication anything went wrong.
      const message = event?.error?.message ?? "Unknown map error";
      // eslint-disable-next-line no-console
      console.error("MapLibre error:", message);
      setMapError((current) => current ?? `Map tiles failed to load (${message}). Check your network connection.`);
    });
    const styleLoadTimeout = window.setTimeout(() => {
      if (!map.isStyleLoaded()) {
        setMapError((current) => current ?? "Map tiles are taking too long to load. Check your network connection.");
      }
    }, 8000);
    const pauseFollow = (event: { originalEvent?: unknown }) => {
      if (!event.originalEvent) {
        return;
      }
      followingRef.current = false;
      setIsFollowing(false);
    };
    map.on("dragstart", pauseFollow);
    map.on("zoomstart", pauseFollow);
    map.on("rotatestart", pauseFollow);
    map.on("style.load", () => {
      window.clearTimeout(styleLoadTimeout);
      try {
        map.addLayer({
          id: "hospital-3d-buildings",
          source: "openmaptiles",
          "source-layer": "building",
          type: "fill-extrusion",
          minzoom: 14,
          paint: {
            "fill-extrusion-color": "#c4ced8",
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], ["get", "height"], 14],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], ["get", "min_height"], 0],
            "fill-extrusion-opacity": 0.34,
          },
        });
      } catch {
        // The navigation route remains usable when a tile style has no building source.
      }
    });
    mapRef.current = map;
    return () => {
      window.clearTimeout(styleLoadTimeout);
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current);
      }
      ambulanceMarkerRef.current?.remove();
      stopMarkersRef.current.forEach((marker) => marker.remove());
      map.remove();
      mapRef.current = null;
      ambulanceMarkerRef.current = null;
      stopMarkersRef.current = [];
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    routeTrackRef.current = track;
    if (!map || !track) {
      return;
    }
    const allCoordinates = track.points.map(([latitude, longitude]) => [longitude, latitude]);
    const applyRoute = () => {
      if (!map.getSource("mission-route-remaining")) {
        map.addSource("mission-route-traveled", { type: "geojson", data: routeFeature(allCoordinates.slice(0, 2)) });
        map.addSource("mission-route-remaining", { type: "geojson", data: routeFeature(allCoordinates) });
        map.addLayer({
          id: "mission-route-shadow",
          type: "line",
          source: "mission-route-remaining",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#06172a", "line-opacity": 0.62, "line-width": 15 },
        });
        map.addLayer({
          id: "mission-route-traveled-line",
          type: "line",
          source: "mission-route-traveled",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#74869a", "line-opacity": 0.78, "line-width": 8 },
        });
        map.addLayer({
          id: "mission-route-line",
          type: "line",
          source: "mission-route-remaining",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": NAVIGATION_ROUTE_COLOR, "line-width": 8 },
        });
      } else {
        (map.getSource("mission-route-remaining") as maplibregl.GeoJSONSource).setData(routeFeature(allCoordinates));
      }

      stopMarkersRef.current.forEach((marker) => marker.remove());
      stopMarkersRef.current = [
        new Marker({ element: stopElement("pickup"), anchor: "center" })
          .setLngLat(allCoordinates[0] as [number, number])
          .addTo(map),
        new Marker({
          element: stopElement(legLabel.toLowerCase().includes("base") ? "base" : "dropoff"),
          anchor: "center",
        })
          .setLngLat(allCoordinates[allCoordinates.length - 1] as [number, number])
          .addTo(map),
      ];
      const bounds = allCoordinates.reduce(
        (current, coordinate) => current.extend(coordinate as [number, number]),
        new LngLatBounds(allCoordinates[0] as [number, number], allCoordinates[0] as [number, number]),
      );
      overviewUntilRef.current = performance.now() + 900;
      map.fitBounds(bounds, { padding: { top: 120, right: 90, bottom: 180, left: 90 }, maxZoom: 17.4, duration: 650 });
      followingRef.current = true;
      setIsFollowing(true);
    };
    if (map.isStyleLoaded()) {
      applyRoute();
    } else {
      map.once("load", applyRoute);
    }
    const initialProjection = ambulance
      ? projectProgress(track, ambulance.latitude, ambulance.longitude)
      : { progress: 0, offset: 0 };
    const reportedProgress = ambulance?.route_progress_m ?? initialProjection.progress;
    const progress = Math.max(0, Math.min(
      initialProjection.offset <= 100 ? reportedProgress : initialProjection.progress,
      track.totalMeters,
    ));
    const initialHeading = ambulance?.heading_degrees ?? headingAtProgress(track, progress);
    motionRef.current = {
      routeKey,
      displayedProgress: progress,
      startProgress: progress,
      targetProgress: progress,
      transitionStartedAt: performance.now(),
      transitionDurationMs: 550,
      authoritativeReceivedAt: performance.now(),
      speedMps: (ambulance?.speed_kph ?? 0) / 3.6,
      heading: initialHeading,
      cameraBearing: initialHeading,
      lastFrameAt: performance.now(),
      lastRoutePaintAt: 0,
    };
  }, [routeKey, track]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ambulance || !track) {
      return;
    }
    const label = ambulance.base_hospital_id ? `H${ambulance.base_hospital_id}` : "AMB";
    if (!ambulanceMarkerRef.current) {
      const element = ambulanceElement(color, label);
      ambulanceElementRef.current = element.querySelector(".vehicle-visual");
      ambulanceMarkerRef.current = new Marker({ element, anchor: "center" })
        .setLngLat([ambulance.longitude, ambulance.latitude])
        .addTo(map);
    } else {
      ambulanceElementRef.current?.style.setProperty("--vehicle-color", color);
    }
    const motion = motionRef.current;
    if (!motion || motion.routeKey !== routeKey) {
      return;
    }
    const projection = projectProgress(track, ambulance.latitude, ambulance.longitude, Math.max(motion.targetProgress - 20, 0));
    const reported = ambulance.route_progress_m ?? projection.progress;
    const reportedPoint = positionAtProgress(track, Math.max(0, Math.min(reported, track.totalMeters)));
    const reportedOffset = haversineMeters(reportedPoint, [ambulance.latitude, ambulance.longitude]);
    const target = reportedOffset <= 100 ? reported : projection.progress;
    const now = performance.now();
    motion.startProgress = motion.displayedProgress;
    motion.targetProgress = Math.max(motion.displayedProgress - 3, Math.min(target, track.totalMeters));
    motion.transitionStartedAt = now;
    motion.transitionDurationMs = 620;
    motion.authoritativeReceivedAt = now;
    motion.speedMps = Math.max(0, (ambulance.speed_kph ?? 0) / 3.6);
  }, [ambulance, color, routeKey, track]);

  useEffect(() => {
    const animate = (now: number) => {
      const map = mapRef.current;
      const activeTrack = routeTrackRef.current;
      const motion = motionRef.current;
      if (map && activeTrack && motion && ambulanceMarkerRef.current) {
        const transitionRatio = Math.max(0, Math.min(
          (now - motion.transitionStartedAt) / Math.max(motion.transitionDurationMs, 1),
          1,
        ));
        const eased = transitionRatio * transitionRatio * (3 - 2 * transitionRatio);
        let progress = motion.startProgress + (motion.targetProgress - motion.startProgress) * eased;
        if (transitionRatio >= 1 && motion.speedMps > 0) {
          const extrapolationSeconds = Math.min((now - motion.authoritativeReceivedAt) / 1000, 0.8);
          progress = Math.min(motion.targetProgress + motion.speedMps * extrapolationSeconds, activeTrack.totalMeters);
        }
        motion.displayedProgress = Math.max(motion.displayedProgress - 0.5, progress);
        const position = positionAtProgress(activeTrack, motion.displayedProgress);
        const targetHeading = headingAtProgress(activeTrack, motion.displayedProgress);
        const deltaMs = Math.max(1, Math.min(now - motion.lastFrameAt, 50));
        motion.lastFrameAt = now;
        motion.heading = interpolateAngle(motion.heading, targetHeading, Math.min(1, deltaMs / 180));
        motion.cameraBearing = interpolateAngle(
          motion.cameraBearing,
          northUpRef.current ? 0 : motion.heading,
          Math.min(1, deltaMs / 260),
        );
        ambulanceMarkerRef.current.setLngLat([position[1], position[0]]);
        if (ambulanceElementRef.current) {
          ambulanceElementRef.current.style.transform = `rotate(${motion.heading - 90}deg)`;
        }
        if (followingRef.current && now >= overviewUntilRef.current) {
          map.jumpTo({
            center: [position[1], position[0]],
            bearing: motion.cameraBearing,
            pitch: 62,
            zoom: 17.8,
            padding: { top: 105, right: 20, bottom: 285, left: 20 },
          });
        }
        if (now - motion.lastRoutePaintAt >= 180) {
          motion.lastRoutePaintAt = now;
          const traveledSource = map.getSource("mission-route-traveled") as maplibregl.GeoJSONSource | undefined;
          const remainingSource = map.getSource("mission-route-remaining") as maplibregl.GeoJSONSource | undefined;
          traveledSource?.setData(routeFeature(routeCoordinates(activeTrack, motion.displayedProgress, true)));
          remainingSource?.setData(routeFeature(routeCoordinates(activeTrack, motion.displayedProgress, false)));
        }
      }
      frameRef.current = requestAnimationFrame(animate);
    };
    frameRef.current = requestAnimationFrame(animate);
    return () => {
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, []);

  function recenter() {
    followingRef.current = true;
    setIsFollowing(true);
    overviewUntilRef.current = 0;
  }

  function showOverview() {
    const map = mapRef.current;
    const activeTrack = routeTrackRef.current;
    if (!map || !activeTrack) {
      return;
    }
    followingRef.current = false;
    setIsFollowing(false);
    const coordinates = activeTrack.points.map(([latitude, longitude]) => [longitude, latitude] as [number, number]);
    const bounds = coordinates.reduce(
      (current, coordinate) => current.extend(coordinate),
      new LngLatBounds(coordinates[0], coordinates[0]),
    );
    map.fitBounds(bounds, { padding: { top: 120, right: 80, bottom: 140, left: 80 }, maxZoom: 17.2, duration: 550 });
  }

  function toggleNorthUp() {
    const next = !northUpRef.current;
    northUpRef.current = next;
    setNorthUp(next);
  }

  return (
    <div className="maplibre-navigation-shell">
      <div ref={containerRef} className="maplibre-navigation-map" />
      {mapError && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            textAlign: "center",
            background: "rgba(244, 246, 248, 0.92)",
            color: "#1a2733",
            fontSize: 13.5,
            zIndex: 5,
          }}
        >
          {mapError}
        </div>
      )}
      <div className="maplibre-navigation-controls">
        <button type="button" className={isFollowing ? "active" : ""} onClick={recenter} title="Recenter on ambulance">
          <LocateFixed size={19} />
        </button>
        <button type="button" onClick={showOverview} title="Show complete route">
          <MapIcon size={19} />
        </button>
        <button type="button" className={northUp ? "active" : ""} onClick={toggleNorthUp} title="Toggle north-up view">
          <Compass size={19} />
        </button>
      </div>
      {!isFollowing && <div className="maplibre-follow-paused">Follow paused</div>}
      {ambulance?.navigation_leg === "off_route" && <div className="maplibre-off-route">Off route - recalculating</div>}
      <div className="maplibre-telemetry-status">
        <span className={ambulance?.speed_kph ? "moving" : ""} />
        {ambulance?.speed_kph ? `${Math.round(ambulance.speed_kph)} km/h` : "Stopped"}
        {hospitals.length ? ` / ${hospitals.length} hospitals online` : ""}
      </div>
    </div>
  );
}
