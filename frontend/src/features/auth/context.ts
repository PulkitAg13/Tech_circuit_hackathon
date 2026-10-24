import { createContext, useContext } from "react";

export interface AuthState {
  token: string | null;
  username: string | null;
  displayName: string | null;
  role: string | null;
}

export interface AuthContextValue extends AuthState {
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (
    username: string,
    password: string,
    role?: string,
    displayName?: string,
  ) => Promise<void>;
  switchRole: (role: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
