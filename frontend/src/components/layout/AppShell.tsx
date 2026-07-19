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

const adminNavGroups: { label: string; items: { to: string; label: string; icon: typeof Activity }[] }[] = [
  {
    label: "Console",
    items: [
      { to: "/overview", label: "Overview", icon: LayoutDashboard },
      { to: "/map", label: "Network map", icon: MapIcon },
      { to: "/transfer", label: "Transfer planner", icon: RouteIcon },
      { to: "/requests", label: "Requests", icon: ListChecks },
      { to: "/fleet", label: "Fleet", icon: Ambulance },
    ],
  },
  {
    label: "Network",
    items: [
      { to: "/capacity", label: "Capacity", icon: Activity },
      { to: "/beds", label: "ICU beds", icon: Bed },
      { to: "/transfers", label: "Transfers", icon: RouteIcon },
      { to: "/alerts", label: "Alerts", icon: Bell },
    ],
  },
];

const crewNavItems = [{ to: "/mission", label: "Active mission", icon: Ambulance }];

const pageTitles: Record<string, string> = {
  "/overview": "Overview",
  "/map": "Network map",
  "/transfer": "Transfer planner",
  "/requests": "Requests",
  "/fleet": "Fleet",
  "/capacity": "Capacity",
  "/beds": "ICU beds",
  "/transfers": "Transfers",
  "/alerts": "Alerts",
  "/mission": "Active mission",
};

export function AppShell() {
  const { user, backendOnline, signOut } = useAuth();
  const location = useLocation();
  const isCrew = Boolean(user?.ambulance_id);
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
          {backendOnline ? "Backend connected" : "Reconnecting…"}
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
            Sign out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h2>{title}</h2>
          <span className="topbar-meta">
            <AlertCircle size={12} style={{ verticalAlign: "-2px", marginRight: 6, opacity: 0.6 }} />
            {new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
          </span>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
