import {
  BrowserRouter,
  HashRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { AuthProvider } from "./features/auth/AuthContext";
import { useAuth } from "./features/auth/context";
import { LoginPage } from "./features/auth/LoginPage";
import { DashboardPage } from "./features/submissions/DashboardPage";
import { SubmissionDetailPage } from "./features/submissions/SubmissionDetailPage";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RootGateway() {
  const { token } = useAuth();
  if (token) return <DashboardPage />;
  return <LoginPage />;
}

const isGitHubPagesHost =
  typeof window !== "undefined" &&
  window.location.hostname.endsWith("github.io");

const RouterComponent = isGitHubPagesHost ? HashRouter : BrowserRouter;

export default function App() {
  return (
    <AuthProvider>
      <RouterComponent>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/welcome" element={<LoginPage />} />
          <Route path="/" element={<RootGateway />} />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/submissions/:id"
            element={
              <RequireAuth>
                <SubmissionDetailPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </RouterComponent>
    </AuthProvider>
  );
}
