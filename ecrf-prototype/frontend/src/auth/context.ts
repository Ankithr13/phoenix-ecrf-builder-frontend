import { createContext } from "react";
import type { Me } from "../api/types";

export interface Auth {
  me: Me | null;
  loading: boolean;
  can: (perm: string) => boolean;
  signIn: (email: string, password: string) => Promise<Me>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<Auth | null>(null);
