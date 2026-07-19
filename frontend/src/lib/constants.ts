export const conditionOptions = ["trauma", "respiratory", "cardiac", "neuro", "pediatric", "maternity", "sepsis"];
export const oxygenOptions = ["normal", "low", "critical"];
export const bloodPressureOptions = ["stable", "unstable", "shock"];
export const consciousnessOptions = ["alert", "reduced", "unconscious"];
export const icuOptions = [
  "General ICU",
  "Trauma ICU",
  "Cardiac ICU",
  "Neuro ICU",
  "Surgical ICU",
  "Pediatric ICU",
  "Maternity ICU",
];

export const simulationScenarioOptions = [
  { id: "baseline", label: "Baseline" },
  { id: "evening_surge", label: "Evening surge" },
  { id: "mass_casualty", label: "Mass casualty" },
  { id: "respiratory_wave", label: "Respiratory wave" },
];

export const ambulanceStatusOptions = [
  "available",
  "repositioning",
  "returning",
  "assigned",
  "en_route",
  "transporting",
  "offline",
];

export const icuBedStatusOptions = [
  "available",
  "occupied",
  "transfer_assigned",
  "reserved",
  "cleaning",
  "maintenance",
];

// Used for map markers (hospitals / ambulances) where each entity needs a
// stable, distinct color derived from its id.
export const hospitalMarkerColors = [
  "#1556b0", "#0b7a75", "#a85520", "#7c3aed", "#c2410c",
  "#be123c", "#047857", "#4338ca", "#b45309",
];
export const ambulanceMarkerColors = [
  "#e11d48", "#2563eb", "#059669", "#d97706", "#7c3aed",
  "#0f766e", "#c026d3", "#ca8a04", "#0284c7", "#dc2626",
];

export function stableColor(value: string, palette: string[]) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}

export function hospitalCode(name: string) {
  return name
    .split(/\s+/)
    .filter((word) => word.length > 0 && word[0] === word[0].toUpperCase())
    .map((word) => word[0])
    .join("")
    .slice(0, 4) || name.slice(0, 3).toUpperCase();
}

// Maps backend urgency/pressure strings to the semantic status tokens
// defined in styles/tokens.css (--status-critical / --status-high / etc).
export function statusTone(level: string | null | undefined): "critical" | "high" | "moderate" | "stable" | "offline" {
  const normalized = (level ?? "").toLowerCase();
  if (normalized === "critical") return "critical";
  if (normalized === "high" || normalized === "elevated") return "high";
  if (normalized === "moderate" || normalized === "stable") return normalized === "stable" ? "stable" : "moderate";
  if (!normalized) return "offline";
  return "moderate";
}
