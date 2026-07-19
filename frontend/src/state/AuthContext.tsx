import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  BACKEND_OFFLINE_MESSAGE,
  apiFetch,
  cookieValue,
  refreshAccessToken,
  setAccessToken,
  setOnAuthenticationFailed,
} from "../lib/api";
import type { AuthTokenResponse, Hospital, UserSummary } from "../types";

type AuthContextValue = {
  isSignedIn: boolean;
  isBootstrapping: boolean;
  user: UserSummary | null;
  hospitals: Hospital[];
  backendOnline: boolean;
  error: string | null;
  loginBusy: boolean;
  loginError: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshHospitals: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [user, setUser] = useState<UserSummary | null>(null);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [backendOnline, setBackendOnline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const bootstrapReadyRef = useRef(false);

  async function loadHospitals(silent = false) {
    try {
      const response = await apiFetch("/api/hospitals");
      if (!response.ok) {
        throw new Error("Unable to load hospitals");
      }
      const data: Hospital[] = await response.json();
      setHospitals(data);
      bootstrapReadyRef.current = true;
      setBackendOnline(true);
      setError((current) => (current === BACKEND_OFFLINE_MESSAGE ? null : current));
    } catch {
      setBackendOnline(false);
      if (!silent || hospitals.length === 0) {
        setError(BACKEND_OFFLINE_MESSAGE);
      }
    }
  }

  useEffect(() => {
    setOnAuthenticationFailed(() => {
      setAccessToken(null);
      setIsSignedIn(false);
      setUser(null);
      setLoginError("Your session expired. Sign in again.");
    });

    (async () => {
      await loadHospitals();
      const restored = await refreshAccessToken();
      if (restored) {
        setAccessToken(restored.access_token);
        setUser(restored.user);
        setIsSignedIn(true);
      }
      setIsBootstrapping(false);
    })();

    const interval = window.setInterval(() => {
      if (!bootstrapReadyRef.current) {
        void loadHospitals(true);
      }
    }, 5000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function signIn(username: string, password: string) {
    setLoginBusy(true);
    setLoginError(null);
    try {
      const response = await apiFetch(
        "/api/auth/login",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: username.trim(), password }),
        },
        false,
      );
      if (!response.ok) {
        throw new Error("Invalid username or password");
      }
      const payload: AuthTokenResponse = await response.json();
      setAccessToken(payload.access_token);
      setUser(payload.user);
      setIsSignedIn(true);
      setLoginError(null);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Unable to sign in");
    } finally {
      setLoginBusy(false);
    }
  }

  async function signOut() {
    const csrfToken = cookieValue("icu_csrf");
    try {
      await apiFetch("/api/auth/logout", {
        method: "POST",
        headers: csrfToken ? { "X-CSRF-Token": csrfToken } : undefined,
      });
    } finally {
      setAccessToken(null);
      setIsSignedIn(false);
      setUser(null);
    }
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      isSignedIn,
      isBootstrapping,
      user,
      hospitals,
      backendOnline,
      error,
      loginBusy,
      loginError,
      signIn,
      signOut,
      refreshHospitals: () => loadHospitals(true),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isSignedIn, isBootstrapping, user, hospitals, backendOnline, error, loginBusy, loginError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
