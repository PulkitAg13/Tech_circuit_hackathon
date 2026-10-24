import { createContext, useContext, useState, type ReactNode } from "react";
import { type TokenResponse, switchRole as apiSwitchRole, login as apiLogin, register as apiRegister } from "../../api/client";

export interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (data: TokenResponse) => void;
  logout: () => void;
  switchPersona: (targetUsername: string, targetRole: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("cg_token"));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem("cg_username"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("cg_role"));

  const loginFn = (data: TokenResponse) => {
    localStorage.setItem("cg_token", data.token);
    localStorage.setItem("cg_username", data.username);
    localStorage.setItem("cg_role", data.role);
    setToken(data.token);
    setUsername(data.username);
    setRole(data.role);
  };

  const logoutFn = () => {
    localStorage.removeItem("cg_token");
    localStorage.removeItem("cg_username");
    localStorage.removeItem("cg_role");
    setToken(null);
    setUsername(null);
    setRole(null);
  };

  const switchPersonaFn = async (targetUsername: string, targetRole: string) => {
    const demoPassword = "demoPassword123!";
    // Try logging in as the dedicated demo persona user first (creative_lead, pulkit_manager, aritra_legal)
    try {
      let data: TokenResponse;
      try {
        data = await apiLogin(targetUsername, demoPassword);
      } catch {
        // If not found or wrong password, try registering or fallback to switch-role
        try {
          data = await apiRegister(targetUsername, demoPassword, targetRole);
        } catch {
          data = await apiSwitchRole(targetRole);
        }
      }
      loginFn(data);
    } catch {
      // Last-resort fallback to backend switch-role
      const data = await apiSwitchRole(targetRole);
      loginFn(data);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        username,
        role,
        isAuthenticated: !!token,
        login: loginFn,
        logout: logoutFn,
        switchPersona: switchPersonaFn,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

