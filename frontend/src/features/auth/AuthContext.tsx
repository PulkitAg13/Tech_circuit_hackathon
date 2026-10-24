import { useState, type ReactNode } from "react";
import { type TokenResponse, switchRole as apiSwitchRole, login as apiLogin, register as apiRegister } from "../../api/client";
import { AuthContext } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("cg_token"));
  const [username, setUsername] = useState<string | null>(() => localStorage.getItem("cg_user"));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem("cg_role"));

  const loginFn = (data: TokenResponse) => {
    localStorage.setItem("cg_token", data.token);
    localStorage.setItem("cg_user", data.username);
    localStorage.setItem("cg_role", data.role);
    setToken(data.token);
    setUsername(data.username);
    setRole(data.role);
  };

  const logoutFn = () => {
    localStorage.removeItem("cg_token");
    localStorage.removeItem("cg_user");
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


