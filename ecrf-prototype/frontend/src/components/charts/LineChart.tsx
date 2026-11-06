/* Hand-rolled SVG line chart. No library. */

interface Series { label: string; color: string; values: number[] }

interface Props {
  labels: string[];
  series: Series[];
  height?: number;
}

const PAD_TOP = 14;
const PAD_BOTTOM = 26;
const PAD_LEFT = 34;
const PAD_RIGHT = 14;
const SLOT_MIN = 64;

export default function LineChart({ labels, series, height = 200 }: Props) {
  const n = labels.length;
  const width = Math.max(820, n * SLOT_MIN + PAD_LEFT + PAD_RIGHT);
  const plotW = width - PAD_LEFT - PAD_RIGHT;
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const x = (i: number) => PAD_LEFT + (n > 1 ? (plotW * i) / (n - 1) : plotW / 2);
  const y = (v: number) => PAD_TOP + plotH - (plotH * v) / max;
  const ticks = max === 1 ? [0, 1] : [0, Math.round(max / 2), max];
  // A long study would otherwise have its week labels running into each other.
  const every = Math.max(1, Math.ceil((n * 64) / width));

  const summary = series.map((s) => `${s.label}: ${s.values.join(", ")}`).join("; ");

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Weeks ${labels[0]} to ${labels[n - 1]}. ${summary}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD_LEFT} x2={width - PAD_RIGHT} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={PAD_LEFT - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{t}</text>
          </g>
        ))}
        {labels.map((l, i) => i % every === 0 && (
          <text key={l} x={x(i)} y={height - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">{l.slice(5)}</text>
        ))}
        {series.map((s) => (
          <g key={s.label}>
            <polyline fill="none" stroke={s.color} strokeWidth="2" points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />
            {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="3" fill={s.color} />)}
          </g>
        ))}
      </svg>
      <div className="chart-legend">
        {series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}
      </div>
    </div>
  );
}
