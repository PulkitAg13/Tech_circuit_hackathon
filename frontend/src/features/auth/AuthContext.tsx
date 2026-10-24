import { useState, useCallback, type ReactNode } from "react";
import {
  login as apiLogin,
  register as apiRegister,
  switchRole as apiSwitchRole,
  type TokenResponse,
} from "../../api/client";
import { AuthContext, type AuthState } from "./context";

function loadFromStorage(): AuthState {
  return {
    token: localStorage.getItem("cg_token"),
    username: localStorage.getItem("cg_username"),
    displayName:
      localStorage.getItem("cg_display_name") ||
      localStorage.getItem("cg_username"),
    role: localStorage.getItem("cg_role"),
  };
}

function saveToStorage(res: TokenResponse) {
  const resolvedDisplayName = res.display_name || res.username;
  localStorage.setItem("cg_token", res.token);
  localStorage.setItem("cg_username", res.username);
  localStorage.setItem("cg_display_name", resolvedDisplayName);
  localStorage.setItem("cg_role", res.role);
}

function clearStorage() {
  localStorage.removeItem("cg_token");
  localStorage.removeItem("cg_username");
  localStorage.removeItem("cg_display_name");
  localStorage.removeItem("cg_role");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadFromStorage);

  const loginFn = useCallback(async (username: string, password: string) => {
    const res = await apiLogin(username, password);
    saveToStorage(res);
    setState({
      token: res.token,
      username: res.username,
      displayName: res.display_name || res.username,
      role: res.role,
    });
  }, []);

  const registerFn = useCallback(
    async (
      username: string,
      password: string,
      role = "creator",
      displayName = "",
    ) => {
      const res = await apiRegister(username, password, role, displayName);
      saveToStorage(res);
      setState({
        token: res.token,
        username: res.username,
        displayName: res.display_name || displayName || res.username,
        role: res.role,
      });
    },
    [],
  );

  const switchRoleFn = useCallback(async (targetRole: string) => {
    const res = await apiSwitchRole(targetRole);
    saveToStorage(res);
    setState((prev) => ({
      token: res.token,
      username: res.username || prev.username,
      displayName: res.display_name || prev.displayName || res.username,
      role: res.role,
    }));
  }, []);

  const logout = useCallback(() => {
    clearStorage();
    setState({ token: null, username: null, displayName: null, role: null });
  }, []);

  return (
    <AuthContext.Provider
      value={{
        ...state,
        isAuthenticated: Boolean(state.token),
        login: loginFn,
        register: registerFn,
        switchRole: switchRoleFn,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
