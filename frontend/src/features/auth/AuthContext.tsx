import { createContext, useContext, useState, type ReactNode } from "react";
import type { TokenResponse } from "../../api/client";

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (data: TokenResponse) => void;
  logout: () => void;
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

  return (
    <AuthContext.Provider
      value={{ token, username, role, isAuthenticated: !!token, login: loginFn, logout: logoutFn }}
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
