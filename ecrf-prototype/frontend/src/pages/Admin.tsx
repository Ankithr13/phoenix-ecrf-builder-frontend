import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, NavLink } from "react-router-dom";
import { api } from "../api/client";
import type { AccessEvent, AdminOrg, AdminUser, ChainRow, Role } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { ROLE_LABEL } from "../format";

type Tab = "users" | "log" | "chain";

/* People, the record of who was granted what, and the two switches on each
   protocol's approval chain. An admin touches no clinical data. */
export default function Admin() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("users");
  if (!can("users.manage")) return <Navigate to="/" replace />;
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Admin</h1>
        <div className="muted small">Accounts, roles and sites, the access record, and the approval chain</div>
      </div>
      <div className="row row-wrap mb-3">
        {([["users", "Users"], ["log", "Access log"], ["chain", "Approval chain"]] as const).map(([k, label]) => (
          <button key={k} type="button" className={`tab${tab === k ? " active" : ""}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      {tab === "users" && <Users />}
      {tab === "log" && <AccessLog />}
      {tab === "chain" && <Chain />}
    </div>
  );
}

function Users() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [fOrg, setFOrg] = useState("");
  const [fRole, setFRole] = useState("");
  const [fActive, setFActive] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [shown, setShown] = useState<{ email: string; password: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const { me } = useAuth();

  const load = useCallback(async () => {
    try {
      setUsers(await api.adminUsers({ org_id: fOrg, role: fRole, active: fActive }));
      setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [fOrg, fRole, fActive]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.adminOrgs().then(setOrgs).catch((e) => setError((e as Error).message)); }, []);

  const allRoles = useMemo(() => Array.from(new Set(orgs.flatMap((o) => o.roles))), [orgs]);
  const sites = orgs.filter((o) => o.type === "site");

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    setSaved(null);
    try { await fn(); await load(); }
    catch (e) { setError((e as Error).message); }
  };
  const reset = (u: AdminUser) => act(async () => {
    const r = await api.adminResetPassword(u.id);
    setShown({ email: u.email, password: r.temporary_password });
  });

  return (
    <>
      {shown && (
        <div className="card card-amber">
          <p className="strong">Temporary password for {shown.email}</p>
          <p className="mono mt-2">{shown.password}</p>
          <p className="muted small mt-2">This is shown once. They must choose a new password when they sign in.</p>
          <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={() => setShown(null)}>Done, I have copied it</button>
        </div>
      )}

      <div className="card">
        <div className="row row-wrap row-between">
          <div className="row row-wrap filters">
            <select className="input" value={fOrg} onChange={(e) => setFOrg(e.target.value)} aria-label="Organisation">
              <option value="">All organisations</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            <select className="input" value={fRole} onChange={(e) => setFRole(e.target.value)} aria-label="Role">
              <option value="">All roles</option>
              {allRoles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
            <select className="input" value={fActive} onChange={(e) => setFActive(e.target.value)} aria-label="Status">
              <option value="">Active and inactive</option>
              <option value="true">Active</option>
              <option value="false">Deactivated</option>
            </select>
          </div>
          {!creating && <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>New user</button>}
        </div>
        {creating && (
          <UserForm orgs={orgs} sites={sites} onCancel={() => setCreating(false)} onSave={(body) => act(async () => {
            const r = await api.adminCreateUser(body);
            setShown({ email: r.user.email, password: r.temporary_password });
            setCreating(false);
          })} />
        )}
      </div>

      <div className="card">
        <table className="table">
          <thead><tr><th>Person</th><th>Organisation</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {(users ?? []).map((u) => (
              <Fragment key={u.id}>
              <tr>
                <td>
                  <div className="strong">{u.name}{u.id === me?.user.id && <span className="muted small"> (you)</span>}</div>
                  <div className="mono xs muted">{u.email}</div>
                </td>
                <td>{u.org.name}</td>
                <td>
                  {ROLE_LABEL[u.role] ?? u.role}
                  {u.role === "monitor" && (
                    <div className="xs muted">sites: {u.monitor_site_ids.map((id) => sites.find((x) => x.id === id)?.code ?? id).join(", ") || "none"}</div>
                  )}
                </td>
                <td>
                  <span className={`pill ${u.is_active ? "chip-teal" : "chip-rust"}`}>{u.is_active ? "active" : "deactivated"}</span>
                  {u.must_change_password && <div className="xs muted mt-2">must change password</div>}
                </td>
                <td className="small muted">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}</td>
                <td className="num">
                  <span className="row row-wrap admin-actions">
                    {u.id === me?.user.id ? (
                      <NavLink to="/change-password" className="btn-link">Change your password</NavLink>
                    ) : (
                      <>
                        <button type="button" className="btn-link" onClick={() => setEditing(editing === u.id ? null : u.id)}>
                          {editing === u.id ? "Close" : "Edit"}
                        </button>
                        <button type="button" className="btn-link" onClick={() => reset(u)}>Reset password</button>
                        <button type="button" className="btn-link" onClick={() => act(() => (u.is_active ? api.adminDeactivate(u.id) : api.adminReactivate(u.id)))}>
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      </>
                    )}
                  </span>
                </td>
              </tr>
              {editing === u.id && (
                <tr>
                  <td colSpan={6}>
                    <UserForm user={u} orgs={orgs} sites={sites} onCancel={() => setEditing(null)} onSave={(body) => act(async () => {
                      await api.adminEditUser(u.id, { role: body.role, org_id: body.org_id, monitor_site_ids: body.monitor_site_ids });
                      setEditing(null);
                      setSaved(`${u.email} saved`);
                    })} />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
            {users && users.length === 0 && <tr><td colSpan={6} className="muted small">No users match these filters.</td></tr>}
          </tbody>
        </table>
        {saved && <p className="ok mt-3">{saved}</p>}
      </div>
      {error && <p className="error mt-3">{error}</p>}
    </>
  );
}

interface FormBody { email: string; name: string; org_id: number; role: Role; monitor_site_ids: number[] }

function UserForm({ user, orgs, sites, onSave, onCancel }: {
  user?: AdminUser; orgs: AdminOrg[]; sites: AdminOrg[];
  onSave: (b: FormBody) => void; onCancel: () => void;
}) {
  const [email, setEmail] = useState(user?.email ?? "");
  const [name, setName] = useState(user?.name ?? "");
  const [orgId, setOrgId] = useState<number | "">(user?.org.id ?? "");
  const [role, setRole] = useState<Role | "">(user?.role ?? "");
  const [monitorSites, setMonitorSites] = useState<number[]>(user?.monitor_site_ids ?? []);
  const roles = orgs.find((o) => o.id === orgId)?.roles ?? [];
  const ok = email.includes("@") && name.trim() && orgId !== "" && role && roles.includes(role);

  return (
    <div className="register mt-3">
      {user
        ? <div className="ctl ctl-wide strong">Editing {user.email}</div>
        : (
          <>
            <label className="ctl">Name<input className="input input-sm" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="ctl">Email<input className="input input-sm" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          </>
        )}
      <label className="ctl">
        Organisation
        <select className="input input-sm" value={orgId} onChange={(e) => { setOrgId(Number(e.target.value)); setRole(""); }}>
          <option value="">—</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      <label className="ctl">
        Role
        <select className="input input-sm" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <option value="">—</option>
          {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>
      </label>
      {role === "monitor" && (
        <div className="ctl ctl-wide">
          Sites this monitor sees
          <div className="row row-wrap">
            {sites.map((x) => (
              <label className="check" key={x.id}>
                <input type="checkbox" checked={monitorSites.includes(x.id)}
                       onChange={(e) => setMonitorSites((p) => (e.target.checked ? [...p, x.id] : p.filter((i) => i !== x.id)))} />
                {x.code}
              </label>
            ))}
          </div>
        </div>
      )}
      <span className="grow" />
      <button type="button" className="btn btn-primary btn-sm" disabled={!ok}
              onClick={() => onSave({ email, name, org_id: Number(orgId), role: role as Role, monitor_site_ids: monitorSites })}>
        {user ? "Save" : "Create user"}
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
    </div>
  );
}

function AccessLog() {
  const [rows, setRows] = useState<AccessEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.adminAccessLog().then(setRows).catch((e) => setError((e as Error).message)); }, []);
  return (
    <div className="card">
      <p className="muted small mb-3">Who was granted what, and by whom. Rows are only ever added.</p>
      <table className="table">
        <thead><tr><th>When</th><th>Person</th><th>What</th><th>By</th><th>Detail</th></tr></thead>
        <tbody>
          {(rows ?? []).map((e) => (
            <tr key={e.id}>
              <td className="small muted">{new Date(e.at).toLocaleString()}</td>
              <td className="mono small">{e.user}</td>
              <td>{e.action.replace(/_/g, " ")}</td>
              <td className="mono small">{e.by}</td>
              <td className="small">{e.detail ?? "—"}</td>
            </tr>
          ))}
          {rows && rows.length === 0 && <tr><td colSpan={5} className="muted small">Nothing recorded yet.</td></tr>}
        </tbody>
      </table>
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}

function Chain() {
  const [rows, setRows] = useState<ChainRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { api.adminChain().then(setRows).catch((e) => setError((e as Error).message)); }, []);
  useEffect(load, [load]);
  const set = async (id: number, patch: Partial<ChainRow>) => {
    setError(null);
    try { await api.adminSetChain(id, patch); load(); }
    catch (e) { setError((e as Error).message); }
  };
  return (
    <div className="card">
      <p className="muted small mb-3">
        The order is fixed: enter, submit, monitor review if required, data manager approval, investigator sign-off if required, study lock.
        The data manager locks the study, on Data review.
      </p>
      <table className="table">
        <thead><tr><th>Protocol</th><th>Monitor review required</th><th>Investigator sign-off required</th></tr></thead>
        <tbody>
          {(rows ?? []).map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td><input type="checkbox" checked={p.monitor_review_required} aria-label={`Monitor review required for ${p.name}`}
                         onChange={(e) => set(p.id, { monitor_review_required: e.target.checked })} /></td>
              <td><input type="checkbox" checked={p.investigator_signature_required} aria-label={`Investigator sign-off required for ${p.name}`}
                         onChange={(e) => set(p.id, { investigator_signature_required: e.target.checked })} /></td>
            </tr>
          ))}
          {rows && rows.length === 0 && <tr><td colSpan={3} className="muted small">No protocols yet.</td></tr>}
        </tbody>
      </table>
      {error && <p className="error mt-3">{error}</p>}
    </div>
  );
}
