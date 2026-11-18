import { useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { NavigationContext } from "../navigation/context";

export default function NavigationActions({ children }: { children: ReactNode }) {
  const context = useContext(NavigationContext);
  return context?.actionsContainer ? createPortal(children, context.actionsContainer) : null;
}
