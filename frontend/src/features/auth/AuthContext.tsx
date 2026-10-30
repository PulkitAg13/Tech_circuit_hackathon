import { useState, useCallback, useEffect, type ReactNode } from "react";
import {
  login as apiLogin,
  register as apiRegister,
  switchRole as apiSwitchRole,
  getMe as apiGetMe,
  isJwtExpired,
  type TokenResponse,
} from "../../api/client";
import { AuthContext, type AuthState } from "./context";

function clearStorage() {
  localStorage.removeItem("cg_token");
  localStorage.removeItem("cg_username");
  localStorage.removeItem("cg_display_name");
  localStorage.removeItem("cg_role");
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem("cg_signed_out", "1");
  }
}

function loadFromStorage(): AuthState {
  const token = localStorage.getItem("cg_token");
  if (!token || isJwtExpired(token)) {
    if (token) {
      clearStorage();
    }
    return {
      token: null,
      username: null,
      displayName: null,
      role: null,
    };
  }
  return {
    token,
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
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.removeItem("cg_signed_out");
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadFromStorage);

  const logout = useCallback(() => {
    clearStorage();
    setState({ token: null, username: null, displayName: null, role: null });
  }, []);

  useEffect(() => {
    function handleAuthExpired() {
      logout();
    }
    function handleAuthRefreshed(e: Event) {
      if (
        typeof sessionStorage !== "undefined" &&
        sessionStorage.getItem("cg_signed_out") === "1"
      ) {
        return;
      }
      const detail = (e as CustomEvent<TokenResponse>).detail;
      if (detail && detail.token) {
        saveToStorage(detail);
        setState({
          token: detail.token,
          username: detail.username,
          displayName: detail.display_name || detail.username,
          role: detail.role,
        });
      }
    }
    window.addEventListener("cg:auth-expired", handleAuthExpired);
    window.addEventListener("cg:auth-refreshed", handleAuthRefreshed);
    return () => {
      window.removeEventListener("cg:auth-expired", handleAuthExpired);
      window.removeEventListener("cg:auth-refreshed", handleAuthRefreshed);
    };
  }, [logout]);

  useEffect(() => {
    if (!state.token) return;
    let active = true;
    void apiGetMe()
      .then((res) => {
        if (!active) return;
        saveToStorage(res);
        setState((prev) => {
          if (
            prev.token === res.token &&
            prev.username === res.username &&
            prev.role === res.role
          ) {
            return prev;
          }
          return {
            token: res.token,
            username: res.username,
            displayName: res.display_name || res.username,
            role: res.role,
          };
        });
      })
      .catch(() => {
        // Handled by 401 interceptor
      });
    return () => {
      active = false;
    };
  }, [state.token]);

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
