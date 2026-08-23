import type { AuthTokenResponse } from "../types";

// In hosted/production builds, set VITE_API_BASE_URL (e.g. on Vercel) to
// your backend's real public URL. When unset — i.e. local development —
// this falls back to exactly the same local candidates as before, so
// nothing changes for local dev.
const envApiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

export const API_BASE_CANDIDATES = Array.from(
  new Set(
    (envApiBase
      ? [envApiBase.replace(/\/+$/, "")]
      : ["http://127.0.0.1:8001", "http://127.0.0.1:8000"]
    ).filter(Boolean) as string[],
  ),
);

let activeApiBase = API_BASE_CANDIDATES[0];
let accessToken: string | null = null;
let refreshPromise: Promise<AuthTokenResponse | null> | null = null;

// The auth layer is intentionally decoupled from React: AuthProvider wires
// this up once at startup so token expiry can trigger a logout anywhere.
let onAuthenticationFailed: () => void = () => {};

export function setOnAuthenticationFailed(handler: () => void) {
  onAuthenticationFailed = handler;
}

export function getActiveApiBase() {
  return activeApiBase;
}

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function cookieValue(name: string) {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((cookie) => cookie.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

export async function refreshAccessToken(): Promise<AuthTokenResponse | null> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = (async () => {
    const csrfToken = cookieValue("icu_csrf");
    if (!csrfToken) {
      return null;
    }
    for (const base of [activeApiBase, ...API_BASE_CANDIDATES.filter((item) => item !== activeApiBase)]) {
      try {
        const response = await fetch(`${base}/api/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": csrfToken },
        });
        if (!response.ok) {
          continue;
        }
        const payload: AuthTokenResponse = await response.json();
        accessToken = payload.access_token;
        activeApiBase = base;
        return payload;
      } catch {
        // Try the next configured backend candidate.
      }
    }
    accessToken = null;
    return null;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function apiFetch(path: string, init?: RequestInit, allowRefresh = true): Promise<Response> {
  let lastError: unknown;
  const orderedBases = [activeApiBase, ...API_BASE_CANDIDATES.filter((base) => base !== activeApiBase)];
  for (const base of orderedBases) {
    try {
      const headers = new Headers(init?.headers);
      if (accessToken) {
        headers.set("Authorization", `Bearer ${accessToken}`);
      }
      const response = await fetch(`${base}${path}`, {
        ...init,
        credentials: "include",
        headers,
      });
      activeApiBase = base;
      const refreshEligible = path !== "/api/auth/login" && path !== "/api/auth/refresh";
      if (response.status === 401 && allowRefresh && refreshEligible) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
          return apiFetch(path, init, false);
        }
        onAuthenticationFailed();
      }
      return response;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError;
}

export function websocketBase() {
  return activeApiBase.replace(/^http/, "ws");
}

// This message is shown to the user when the backend can't be reached.
// Previously referenced START_APP.cmd, a local-only Windows launcher that
// was removed from the project and makes no sense to a hosted user anyway.
export const BACKEND_OFFLINE_MESSAGE =
  "Backend is temporarily unavailable. Reconnecting automatically\u2026";
