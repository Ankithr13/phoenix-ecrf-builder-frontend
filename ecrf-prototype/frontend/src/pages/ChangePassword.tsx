import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";

/* The only screen a temporary password can reach. Also where anyone can
   change their own password. */
export default function ChangePassword() {
  const { me, loading, changePassword, signOut } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && !me) return <Navigate to="/login" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) { setError("The two new passwords are different"); return; }
    setBusy(true); setError(null);
    try {
      await changePassword(current, next);
      navigate("/", { replace: true });
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : null;
      setError(typeof detail === "string" ? detail : "Could not change the password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">Choose a new password</h1>
        <p className="login-sub">
          {me?.must_change_password ? "You signed in with a temporary password. Choose your own to continue." : "At least 8 characters."}
        </p>
        <form className="login-form" onSubmit={submit} noValidate>
          <label className="label" htmlFor="current">Current password</label>
          <input id="current" className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />
          <label className="label" htmlFor="next">New password</label>
          <input id="next" className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          <label className="label" htmlFor="again">New password again</label>
          <input id="again" className="input" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
          {error && <div className="login-error" role="alert">{error}</div>}
          <button type="submit" className="login-btn" disabled={busy || !current || next.length < 8 || !again}>
            {busy ? "Saving…" : "Save new password"}
          </button>
        </form>
        <button type="button" className="btn-link mt-3" onClick={signOut}>Sign out</button>
      </div>
    </div>
  );
}
