import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProtocolListItem } from "../api/types";
import { useAuth } from "../auth/useAuth";

export function useProtocols(enabled = true) {
  const { me } = useAuth();
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([me?.user.id, attempt, enabled]);
  const [result, setResult] = useState<{ key: string; rows: ProtocolListItem[]; error: string | null } | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    api.listProtocols().then((rows) => { if (active) setResult({ key, rows, error: null }); })
      .catch(() => { if (active) setResult({ key, rows: [], error: "Could not load protocols. Retry to see the current workspace." }); });
    return () => { active = false; };
  }, [key, enabled]);
  const current = result?.key === key ? result : null;
  return { rows: enabled ? current?.rows ?? [] : [], loading: enabled && !current, error: enabled ? current?.error ?? null : null, refresh: () => setAttempt((previous) => previous + 1) };
}
