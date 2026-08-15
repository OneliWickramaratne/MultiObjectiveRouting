import { useMemo, useState } from "react";
import { AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { useAuth } from "../state/AuthContext";
import { hospitalCode } from "../lib/constants";
import { useLanguage } from "../i18n/LanguageContext";
import { LanguageSwitcher } from "../components/LanguageSwitcher";

export function LoginPage() {
  const { hospitals, backendOnline, loginBusy, loginError, signIn } = useAuth();
  const { t } = useLanguage();
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
          <h1>{t.login.heroTitle}</h1>
          <p>{t.login.heroSubtitle}</p>
          <div className="login-metrics">
            <div>
              <strong>{hospitals.length || 9}</strong>
              <span>{t.login.hospitalsLabel}</span>
            </div>
            <div>
              <strong>{totals.totalBeds || "—"}</strong>
              <span>{t.login.icuBedsLabel}</span>
            </div>
            <div>
              <strong>{totals.availableBeds || "—"}</strong>
              <span>{t.login.openNowLabel}</span>
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
              <h2>{t.login.title}</h2>
              <p>{t.login.subtitle}</p>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h1 style={{ margin: 0 }}>{t.login.welcomeBack}</h1>
            <LanguageSwitcher compact />
          </div>
          <p className="lede">{t.login.signInPrompt}</p>

          <label className="login-field">
            {t.login.username}
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Your assigned username"
            />
          </label>
          <label className="login-field">
            {t.login.password}
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t.login.password}
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
                <Loader2 size={16} className="spin" /> {t.login.signingIn}
              </>
            ) : (
              t.login.signIn
            )}
          </button>

          <div className={backendOnline ? "login-system-ready online" : "login-system-ready"}>
            <span className="dot" />
            {backendOnline ? t.login.systemReady : t.login.connecting}
          </div>
        </form>
      </section>
    </main>
  );
}
