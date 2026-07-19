import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./state/AuthContext";
import { AppShell } from "./components/layout/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { TransferPlannerPage } from "./pages/TransferPlannerPage";
import { RequestsPage } from "./pages/RequestsPage";
import { FleetPage } from "./pages/FleetPage";
import { IcuBedsPage } from "./pages/IcuBedsPage";
import { CapacityPage } from "./pages/CapacityPage";
import { TransfersPage } from "./pages/TransfersPage";
import { AlertsPage } from "./pages/AlertsPage";
import { MissionPage } from "./pages/MissionPage";
import { NetworkMapPage } from "./pages/NetworkMapPage";

function Gate() {
  const { isSignedIn, isBootstrapping, user } = useAuth();
  const location = useLocation();

  if (isBootstrapping) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", color: "var(--text-dim)" }}>
        Loading command console…
      </div>
    );
  }

  if (!isSignedIn) {
    return <LoginPage />;
  }

  const isCrew = Boolean(user?.ambulance_id);
  const currentPath = location.pathname;

  // Guard against stale/typed-in URLs that don't match the signed-in role:
  // ambulance crew only ever see the mission view, admins never see it.
  if (isCrew && currentPath !== "/mission") {
    return <Navigate to="/mission" replace />;
  }
  if (!isCrew && currentPath === "/mission") {
    return <Navigate to="/overview" replace />;
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/map" element={<NetworkMapPage />} />
        <Route path="/transfer" element={<TransferPlannerPage />} />
        <Route path="/requests" element={<RequestsPage />} />
        <Route path="/fleet" element={<FleetPage />} />
        <Route path="/capacity" element={<CapacityPage />} />
        <Route path="/beds" element={<IcuBedsPage />} />
        <Route path="/transfers" element={<TransfersPage />} />
        <Route path="/analytics" element={<Navigate to="/capacity" replace />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/mission" element={<MissionPage />} />
        <Route path="*" element={<Navigate to={isCrew ? "/mission" : "/overview"} replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
