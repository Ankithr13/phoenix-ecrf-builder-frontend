import { useEffect, useState } from "react";
import { useMatch } from "react-router-dom";
import { api } from "../api/client";
import type { NavigationContextData } from "../api/types";
import { useAuth } from "../auth/useAuth";

type StudyContext = NavigationContextData["study"];
type ContextResult = { key: string; data: NavigationContextData | null; study: StudyContext; error: boolean };

export function useNavigationState() {
  const { me } = useAuth();
  const sponsorProtocol = useMatch("/sponsor/p/:protocolId/:section");
  const sitePatients = useMatch("/site/s/:protocolId/patients");
  const sitePatient = useMatch("/site/s/:protocolId/patients/:subject");
  const studyRoute = useMatch("/sponsor/studies/:studyId");
  const protocolId = sponsorProtocol?.params.protocolId ?? sitePatient?.params.protocolId ?? sitePatients?.params.protocolId ?? null;
  const studyId = studyRoute?.params.studyId ?? null;
  const subject = sitePatient?.params.subject;
  const section = sponsorProtocol?.params.section ?? (sitePatient ? "entry" : sitePatients ? "patients" : null);
  const [result, setResult] = useState<ContextResult | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const key = JSON.stringify([me?.user.id, protocolId, studyId, subject, retryCount]);

  useEffect(() => {
    if (!protocolId && !studyId) return;
    let active = true;
    const load = async () => {
      try {
        if (protocolId) {
          const data = await api.navigationContext(protocolId, subject);
          if (active) setResult({ key, data, study: data.study, error: false });
        } else if (studyId) {
          const study = await api.sponsorStudy(Number(studyId));
          if (active) setResult({ key, data: null, study, error: false });
        }
      } catch {
        if (active) setResult({ key, data: null, study: null, error: true });
      }
    };
    void load();
    return () => { active = false; };
  }, [key, protocolId, studyId, subject]);

  const current = result?.key === key ? result : null;
  return {
    protocolId, studyId, section,
    data: current?.data ?? null, study: current?.study ?? null,
    loading: Boolean((protocolId || studyId) && !current), error: current?.error ?? false,
    retry: () => setRetryCount((previous) => previous + 1),
  };
}
