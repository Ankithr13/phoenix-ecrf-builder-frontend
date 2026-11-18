import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { protocolStage } from "../workspace/protocolPresentation";
import { useProtocols } from "./useProtocols";

export interface WorkspaceCounts {
  studies: number | null;
  protocols: number;
  pending_reviews: number;
  queries_for_me: number | null;
  locked_protocols: number;
  unextracted_protocols: number;
}

export function useWorkspaceOverview() {
  const { me, can } = useAuth();
  const protocols = useProtocols();
  const [attempt, setAttempt] = useState(0);
  const permitted = can("query.raise") || can("query.answer") || can("query.close");
  const key = JSON.stringify([me?.user.id, me?.role, attempt]);
  const [queries, setQueries] = useState<{ key: string; count: number | null } | null>(null);
  useEffect(() => {
    if (!permitted || !me || me.must_change_password) return;
    let active = true;
    api.queries().then((rows) => {
      if (active) setQueries({ key, count: rows.filter((query) => query.for_me).length });
    }).catch(() => { if (active) setQueries({ key, count: null }); });
    return () => { active = false; };
  }, [key, permitted, me]);
  const counts: WorkspaceCounts = {
    studies: null,
    protocols: protocols.rows.length,
    pending_reviews: protocols.rows.filter((protocol) => protocolStage(protocol) === "draft").length,
    queries_for_me: permitted && queries?.key === key ? queries.count : null,
    locked_protocols: protocols.rows.filter((protocol) => protocolStage(protocol) === "locked").length,
    unextracted_protocols: protocols.rows.filter((protocol) => protocolStage(protocol) === "not_extracted").length,
  };
  return {
    overview: protocols.loading || protocols.error ? null : { counts },
    refreshing: protocols.loading,
    error: protocols.error,
    refresh: () => { protocols.refresh(); setAttempt((previous) => previous + 1); },
  };
}
