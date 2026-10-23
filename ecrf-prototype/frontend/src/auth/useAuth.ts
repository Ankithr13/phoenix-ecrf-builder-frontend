import { useContext } from "react";
import { AuthContext, type Auth } from "./context";

export function useAuth(): Auth {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
