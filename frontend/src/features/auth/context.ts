import { createContext } from "react";
import type { TokenResponse } from "../../api/client";

export interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (data: TokenResponse) => void;
  logout: () => void;
  switchPersona: (targetUsername: string, targetRole: string) => Promise<void>;
}


export const AuthContext = createContext<AuthState | null>(null);
