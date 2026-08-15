import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  Ambulance,
  Bed,
  Bell,
  LayoutDashboard,
  ListChecks,
  Map as MapIcon,
  Route as RouteIcon,
  ShieldCheck,
  UserCog,
} from "lucide-react";
import { useAuth } from "../../state/AuthContext";
import { useLanguage } from "../../i18n/LanguageContext";
import { LanguageSwitcher } from "../LanguageSwitcher";
import type { TranslationKeys } from "../../i18n/translations";

function buildAdminNavGroups(t: TranslationKeys) {
  return [
    {
      label: "Console",
      items: [
        { to: "/overview", label: t.nav.overview, icon: LayoutDashboard },
        { to: "/map", label: t.nav.networkMap, icon: MapIcon },
        { to: "/transfer", label: t.nav.transferPlanner, icon: RouteIcon },
        { to: "/requests", label: t.nav.requests, icon: ListChecks },
        { to: "/fleet", label: t.nav.fleet, icon: Ambulance },
      ],
    },
    {
      label: "Network",
      items: [
        { to: "/capacity", label: t.nav.capacity, icon: Activity },
        { to: "/beds", label: t.nav.icuBeds, icon: Bed },
        { to: "/transfers", label: t.nav.transfers, icon: RouteIcon },
        { to: "/alerts", label: t.nav.alerts, icon: Bell },
      ],
    },
  ];
}

export function AppShell() {
  const { user, backendOnline, signOut } = useAuth();
  const { t } = useLanguage();
  const location = useLocation();
  const isCrew = Boolean(user?.ambulance_id);

  const adminNavGroups = buildAdminNavGroups(t);
  const crewNavItems = [{ to: "/mission", label: t.nav.activeMission, icon: Ambulance }];
  const pageTitles: Record<string, string> = {
    "/overview": t.nav.overview,
    "/map": t.nav.networkMap,
    "/transfer": t.nav.transferPlanner,
    "/requests": t.nav.requests,
    "/fleet": t.nav.fleet,
    "/capacity": t.nav.capacity,
    "/beds": t.nav.icuBeds,
    "/transfers": t.nav.transfers,
    "/alerts": t.nav.alerts,
    "/mission": t.nav.activeMission,
  };
  const title = pageTitles[location.pathname] ?? "ICU Command";

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-brand">
          <span className="mark">
            <ShieldCheck size={18} />
          </span>
          <div>
            <h1>ICU Command</h1>
            <p>Colombo transfer network</p>
          </div>
        </div>

        <div className={backendOnline ? "rail-status online" : "rail-status"}>
          <span className="dot" />
          {backendOnline ? t.shell.networkConnected : t.shell.networkReconnecting}
        </div>

        {isCrew ? (
          <nav className="rail-nav" aria-label="Crew navigation">
            <div className="rail-nav-label">Crew</div>
            {crewNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => (isActive ? "rail-link active" : "rail-link")}
              >
                <item.icon size={16} /> {item.label}
              </NavLink>
            ))}
          </nav>
        ) : (
          adminNavGroups.map((group) => (
            <nav className="rail-nav" aria-label={group.label} key={group.label}>
              <div className="rail-nav-label">{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => (isActive ? "rail-link active" : "rail-link")}
                >
                  <item.icon size={16} /> {item.label}
                </NavLink>
              ))}
            </nav>
          ))
        )}

        <div className="rail-footer">
          <div className="rail-operator">
            <span className="avatar">
              <UserCog size={15} />
            </span>
            <div>
              <strong>{user?.name ?? "Operator"}</strong>
              <span>{user?.role?.split("_").join(" ")}</span>
            </div>
          </div>
          <button type="button" className="rail-signout" onClick={() => void signOut()}>
            {t.common.signOut}
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h2>{title}</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <LanguageSwitcher compact />
            <span className="topbar-meta">
              <AlertCircle size={12} style={{ verticalAlign: "-2px", marginRight: 6, opacity: 0.6 }} />
              {new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
            </span>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
