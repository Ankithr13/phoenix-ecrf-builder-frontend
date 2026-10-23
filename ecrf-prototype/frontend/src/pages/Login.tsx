import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";

const DEMO = [
  ["builder@phoenix.demo", "sponsor · builder"],
  ["approver@phoenix.demo", "sponsor · approver"],
  ["staff@bgh.demo", "site · Boston General"],
  ["staff@mrc.demo", "site · Mercy Hospital"],
];

export default function Login() {
  const { me, loading, signIn } = useAuth();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && me) return <Navigate to={params.get("next") || "/"} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await signIn(email, password);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(status === 429
        ? "Too many attempts. Try again in a few minutes."
        : "Email or password is incorrect");
    } finally {
      setBusy(false);
    }
  };

  const invalid = error ? " input-invalid" : "";

  return (
    <div className="login-page">
      <div className="login-card">
        <img className="login-logo" src="/logo.png" alt="Phoenix Clinical Research" />
        <h1 className="login-title">Sign in</h1>
        <p className="login-sub">Electronic case report forms for clinical research</p>

        <form className="login-form" onSubmit={submit} noValidate>
          <label className="label" htmlFor="email">Email</label>
          <input
            id="email" className={`input${invalid}`} type="email" autoComplete="username"
            value={email} onChange={(e) => setEmail(e.target.value)} autoFocus
          />
          <label className="label" htmlFor="password">Password</label>
          <input
            id="password" className={`input${invalid}`} type="password" autoComplete="current-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="login-error" role="alert">{error}</div>}
          <button type="submit" className="login-btn" disabled={busy || !email || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>

      <div className="login-foot">
        <div>BU Spark! × Phoenix Clinical — prototype</div>
        {import.meta.env.DEV && (
          <div className="login-demo">
            {DEMO.map(([e, who]) => (
              <button type="button" key={e} className="login-demo-row" onClick={() => { setEmail(e); setPassword("demo1234"); }}>
                <span className="mono">{e}</span><span>{who}</span>
              </button>
            ))}
            <div className="login-demo-note">password demo1234 · click a row to fill the form</div>
          </div>
        )}
      </div>
    </div>
  );
}
