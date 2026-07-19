import { useMemo, useState } from "react";
import { AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { useAuth } from "../state/AuthContext";
import { hospitalCode } from "../lib/constants";

export function LoginPage() {
  const { hospitals, backendOnline, loginBusy, loginError, signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const totals = useMemo(() => {
    const totalBeds = hospitals.reduce((sum, h) => sum + h.total_beds, 0);
    const availableBeds = hospitals.reduce((sum, h) => sum + h.available_beds, 0);
    return { totalBeds, availableBeds };
  }, [hospitals]);

  return (
    <main className="login-screen">
      <section className="login-stage" aria-hidden="true">
        <div className="login-stage-grid" />
        <div className="login-eyebrow">
          <ShieldCheck size={14} /> Colombo Emergency Network
        </div>
        <div className="login-headline">
          <h1>ICU Capacity-Aware Emergency Transfer Console</h1>
          <p>
            Live bed capacity, urgency-aware routing, and ambulance dispatch across nine
            Colombo hospitals — coordinated from one command console.
          </p>
          <div className="login-metrics">
            <div>
              <strong>{hospitals.length || 9}</strong>
              <span>Hospitals</span>
            </div>
            <div>
              <strong>{totals.totalBeds || "—"}</strong>
              <span>ICU beds</span>
            </div>
            <div>
              <strong>{totals.availableBeds || "—"}</strong>
              <span>Open now</span>
            </div>
          </div>
        </div>
        <div style={{ position: "relative", display: "flex", gap: 8, flexWrap: "wrap", maxWidth: 420 }}>
          {hospitals.slice(0, 9).map((hospital) => (
            <span
              key={hospital.id}
              className="pill tone-stable"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {hospitalCode(hospital.name)}
            </span>
          ))}
        </div>
      </section>

      <section className="login-form-wrap">
        <form
          className="login-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (username && password && !loginBusy) {
              void signIn(username, password);
            }
          }}
        >
          <div className="login-form-head">
            <span className="mark">
              <ShieldCheck size={20} />
            </span>
            <div>
              <h2>ICU Command</h2>
              <p>Sri Lanka Ministry of Health</p>
            </div>
          </div>

          <h1>Welcome back</h1>
          <p className="lede">Sign in to access the command console.</p>

          <label className="login-field">
            Username
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Your assigned username"
            />
          </label>
          <label className="login-field">
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
            />
          </label>

          {loginError && (
            <div className="login-error" role="alert">
              <AlertCircle size={15} /> {loginError}
            </div>
          )}

          <button type="submit" className="login-submit" disabled={!username.trim() || !password || loginBusy}>
            {loginBusy ? (
              <>
                <Loader2 size={16} className="spin" /> Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>

          <div className={backendOnline ? "login-system-ready online" : "login-system-ready"}>
            <span className="dot" />
            {backendOnline ? "All hospital services operational" : "Connecting to hospital services…"}
          </div>
        </form>
      </section>
    </main>
  );
}
