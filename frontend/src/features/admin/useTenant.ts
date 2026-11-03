import { useAuth } from "@/shared/auth/useAuth";

export function useTenantId(): string | null {
  return useAuth().session?.principal.tenant_id ?? null;
}
