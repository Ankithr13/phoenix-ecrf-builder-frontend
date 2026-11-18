import { createContext } from "react";
type NavigationContextData = { protocol: { id: number; name: string; state: "draft" | "locked" | null } };

export interface NavigationState {
  protocolId: string | null;
  section: string | null;
  data: NavigationContextData | null;
  loading: boolean;
  error: boolean;
  retry: () => void;
  actionsContainer: HTMLDivElement | null;
  registerLeaveGuard: (guard: ((action: () => void) => void) | null) => void;
}

export const NavigationContext = createContext<NavigationState | null>(null);
