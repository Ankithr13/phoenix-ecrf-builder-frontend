import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { NavigationState } from "./context";

type ContextData = { protocol: { id: number; name: string; state: "draft" | "locked" | null } };

export function useNavigationState(): Omit<NavigationState, "actionsContainer" | "registerLeaveGuard"> {
  const { me } = useAuth();
  const { pathname } = useLocation();
  const match = pathname.match(/^\/(?:sponsor\/p|site\/s|listing)\/(\d+)(?:\/([^/]+))?/);
  const protocolId = match?.[1] ?? null;
  const section = pathname.startsWith("/listing/") ? "listing" : pathname.includes("/patients/") ? "entry" : match?.[2] ?? null;
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([me?.user.id, protocolId, attempt]);
  const [result, setResult] = useState<{ key: string; data: ContextData | null; error: boolean } | null>(null);
  useEffect(() => {
    if (!protocolId || !me || me.must_change_password) return;
    let active = true;
    api.draft(Number(protocolId)).then((response) => {
      if (active) setResult({ key, data: { protocol: { id: response.protocol.id, name: response.protocol.name, state: response.state ?? null } }, error: false });
    }).catch(() => { if (active) setResult({ key, data: null, error: true }); });
    return () => { active = false; };
  }, [key, protocolId, me]);
  const current = result?.key === key ? result : null;
  return { protocolId, section, data: current?.data ?? null, loading: Boolean(protocolId && !current), error: current?.error ?? false, retry: () => setAttempt((previous) => previous + 1) };
}
