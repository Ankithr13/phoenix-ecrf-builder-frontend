export interface HistoryLine {
  key: string | number;
  label?: string;
  old_value: string | null;
  new_value: string | null;
  who: string;
  when: string;
  reason: string | null;
}

/* The clock on a value or a field. No icon library: this is the whole icon. */
export function HistoryButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" className="icon-btn" onClick={onClick} aria-label={label} title={label}>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 4.2V8l2.6 1.6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/* Old value, new value, who, when, why: for a value or for a form field. */
export default function HistoryDrawer({ title, lines, onClose }: { title: string; lines: HistoryLine[] | null; onClose: () => void }) {
  return (
    <aside className="side-panel" aria-label={title}>
      <div className="row row-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}>{title}</div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
      </div>
      {lines === null && <p className="muted small">Loading…</p>}
      {lines && lines.length === 0 && <p className="muted small">No changes recorded.</p>}
      {lines && lines.map((h) => (
        <div className="history-row" key={h.key}>
          {h.label && <div className="strong small">{h.label}</div>}
          <div className="mono small">
            <span className="muted">{h.old_value ?? "—"}</span> → {h.new_value ?? "—"}
          </div>
          <div className="xs muted">{h.who} · {new Date(h.when).toLocaleString()}</div>
          {h.reason && <div className="small">{h.reason}</div>}
        </div>
      ))}
    </aside>
  );
}
