import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, setUnauthorizedHandler } from "../api/client";
import type { Me } from "../api/types";
import { AuthContext, type Auth } from "./context";

/* Loads /api/auth/me once on start and keeps the signed-in user for the
   whole app. A 401 from any later call clears it and sends the user to the
   login page with the page they wanted in ?next=. */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();
  const here = useRef(location);
  here.current = location;

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setMe(null);
      const { pathname, search } = here.current;
      if (!pathname.startsWith("/login")) {
        navigate(`/login?next=${encodeURIComponent(pathname + search)}`, { replace: true });
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  useEffect(() => {
    api.me()
      .then(setMe)
      .catch((e) => { if (!(e instanceof ApiError && e.status === 401)) console.error(e); setMe(null); })
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const m = await api.login(email, password);
    setMe(m);
    return m;
  }, []);

  const signOut = useCallback(async () => {
    try { await api.logout(); } finally { setMe(null); navigate("/login", { replace: true }); }
  }, [navigate]);

  const value = useMemo<Auth>(() => ({
    me, loading,
    can: (perm) => !!me && me.permissions.includes(perm),
    signIn, signOut,
  }), [me, loading, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
