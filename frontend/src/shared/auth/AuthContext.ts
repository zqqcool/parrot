import { createContext } from "react";

import type { SessionData } from "@/shared/api/types";

export type AuthContextValue = {
  session: SessionData | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
