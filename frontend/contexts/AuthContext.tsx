"use client";

import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/router";

import { authApi, clearTokens, getAccessToken, type User } from "../lib/api";

type AuthResult = { success: true } | { success: false; error: string };

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<AuthResult>;
  register: (email: string, password: string) => Promise<AuthResult>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const PUBLIC_AUTH_BOOTSTRAP_PATHS = new Set(["/", "/login", "/register"]);

function shouldAttemptSilentRefresh(pathname: string): boolean {
  return !PUBLIC_AUTH_BOOTSTRAP_PATHS.has(pathname);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const { push } = router;
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const checkAuth = useCallback(async () => {
    setLoading(true);

    try {
      const token = getAccessToken();
      if (!token && !shouldAttemptSilentRefresh(router.pathname)) {
        setUser(null);
        setError(null);
        return;
      }

      if (!token) {
        await authApi.refreshToken();
      }
      const userData = await authApi.getMe();
      setUser(userData);
      setError(null);
    } catch {
      setUser(null);
      clearTokens();
    } finally {
      setLoading(false);
    }
  }, [router.pathname]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    void checkAuth();
  }, [checkAuth, router.isReady]);

  const login = useCallback(
    async (email: string, password: string): Promise<AuthResult> => {
      setError(null);
      try {
        await authApi.login(email, password);
        const userData = await authApi.getMe();
        setUser(userData);
        push("/companies");
        return { success: true };
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: any } })?.response?.data?.detail ||
          (err as { response?: { data?: any } })?.response?.data?.error ||
          "Login failed. Please check your credentials.";
        setError(message);
        return { success: false, error: message };
      }
    },
    [push],
  );

  const register = useCallback(
    async (email: string, password: string): Promise<AuthResult> => {
      setError(null);
      try {
        await authApi.register(email, password);
        push("/login?registered=true");
        return { success: true };
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: any } })?.response?.data?.email?.[0] ||
          (err as { response?: { data?: any } })?.response?.data?.password?.[0] ||
          (err as { response?: { data?: any } })?.response?.data?.detail ||
          (err as { response?: { data?: any } })?.response?.data?.error ||
          "Registration failed. Please try again.";
        setError(message);
        return { success: false, error: message };
      }
    },
    [push],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (err: unknown) {
      console.error("Logout error:", err);
    } finally {
      setUser(null);
      push("/login");
    }
  }, [push]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      error,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
      checkAuth,
      clearError,
    }),
    [user, loading, error, login, register, logout, checkAuth, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = use(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
