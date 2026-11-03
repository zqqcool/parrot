import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi, http } from "@/shared/api/client";
import type { SessionData } from "@/shared/api/types";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import { HttpClientError } from "@/shared/http";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<SessionData | null>(null);
  const [sessionInitialized, setSessionInitialized] = useState(false);
  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: authApi.session,
    retry: false,
  });

  const clearSession = useCallback(() => {
    setSession(null);
    setSessionInitialized(true);
    http.setCsrfToken(null);
    queryClient.removeQueries({ queryKey: ["admin"] });
  }, [queryClient]);

  const acceptSession = useCallback((next: SessionData) => {
    setSession(next);
    setSessionInitialized(true);
    http.setCsrfToken(next.csrf_token);
  }, []);

  useEffect(() => {
    if (sessionQuery.data) acceptSession(sessionQuery.data);
    if (sessionQuery.error instanceof HttpClientError && sessionQuery.error.status === 401) {
      clearSession();
    }
  }, [acceptSession, clearSession, sessionQuery.data, sessionQuery.error]);

  useEffect(() => {
    http.onUnauthorized(clearSession);
    return () => http.onUnauthorized(null);
  }, [clearSession]);

  const login = useCallback(
    async (username: string, password: string) =>
      acceptSession(await authApi.login(username, password)),
    [acceptSession],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const refreshSession = useCallback(
    async () => acceptSession(await authApi.session()),
    [acceptSession],
  );

  const switchTenant = useCallback(
    async (tenantId: string) => {
      acceptSession(await authApi.switchTenant(tenantId));
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    [acceptSession, queryClient],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      loading: sessionQuery.isPending || (!sessionInitialized && sessionQuery.data !== undefined),
      login,
      logout,
      refreshSession,
      switchTenant,
      hasPermission: (permission) => session?.principal.permissions.includes(permission) ?? false,
    }),
    [
      login,
      logout,
      refreshSession,
      session,
      sessionInitialized,
      sessionQuery.data,
      sessionQuery.isPending,
      switchTenant,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
