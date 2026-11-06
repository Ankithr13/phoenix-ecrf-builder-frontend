import { createContext } from "react";
import type { NavigationContextData } from "../api/types";

export interface NavigationState {
  protocolId: string | null;
  studyId: string | null;
  section: string | null;
  data: NavigationContextData | null;
  study: { id: number; name: string; code: string } | null;
  loading: boolean;
  error: boolean;
  retry: () => void;
  actionsContainer: HTMLDivElement | null;
  registerLeaveGuard: (guard: ((action: () => void) => void) | null) => void;
}

export const NavigationContext = createContext<NavigationState | null>(null);
