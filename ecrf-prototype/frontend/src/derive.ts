import type { FieldDef } from "./api/types";

/* Mirrors backend/ecrf/derive.py. The server is the guarantee: it refuses
   a derived value that disagrees with its inputs. This copy fills the
   derived field in as the inputs are typed and shows the working. */

type Table = Record<string, { codes: string[]; pattern: RegExp }>;

export const INPUTS: Table = {
  weight: { codes: ["WEIGHT"], pattern: /\b(body )?weight\b/ },
  height: { codes: ["HEIGHT"], pattern: /\b(body )?height\b/ },
  sbp: { codes: ["SYSBP"], pattern: /\bsystolic\b/ },
  dbp: { codes: ["DIABP"], pattern: /\bdiastolic\b/ },
  hr: { codes: ["PULSE", "EGHR"], pattern: /\b(heart rate|pulse)\b/ },
  qt: { codes: ["QT"], pattern: /\bqt\b(?!c)|\bqt interval\b|\buncorrected qt\b/ },
  rr: { codes: ["RR"], pattern: /\brr interval\b/ },
  creat: { codes: ["CREAT"], pattern: /\b(serum )?creatinine\b/ },
};
export const DERIVED: Table = {
  bmi: { codes: ["BMI"], pattern: /\bbmi\b|body mass index/ },
  bsa: { codes: [], pattern: /\bbsa\b|body surface area/ },
  map: { codes: [], pattern: /\bmean arterial pressure\b|\bmap\b/ },
  pulse_pressure: { codes: [], pattern: /\bpulse pressure\b/ },
  qtcf: { codes: ["QTCF"], pattern: /\bqtcf\b|fridericia/ },
  egfr: { codes: ["EGFR"], pattern: /\begfr\b|glomerular filtration/ },
};
export const LABEL: Record<string, string> = {
  bmi: "BMI", bsa: "Body surface area", map: "Mean arterial pressure", pulse_pressure: "Pulse pressure",
  qtcf: "QTcF", egfr: "eGFR (CKD-EPI 2021)",
};

export interface Derived { key: string; value: number; unit: string; from: string }

export function roleOf(f: FieldDef, table: Table): string | null {
  for (const [k, t] of Object.entries(table)) if (f.cdash && t.codes.includes(f.cdash)) return k;
  const n = f.name.toLowerCase();
  for (const [k, t] of Object.entries(table)) if (t.pattern.test(n)) return k;
  return null;
}

const kg = (v: number, u?: string | null) => (["lb", "lbs", "pound", "pounds"].includes((u ?? "kg").toLowerCase()) ? v * 0.45359237 : v);
const cm = (v: number, u?: string | null) => {
  const x = (u ?? "cm").toLowerCase();
  if (["m", "metre", "metres", "meter", "meters"].includes(x)) return v * 100;
  if (["in", "inch", "inches"].includes(x)) return v * 2.54;
  return v;
};
const ms = (v: number, u?: string | null) => (["s", "sec", "seconds", "second"].includes((u ?? "ms").toLowerCase()) ? v * 1000 : v);
const mgdl = (v: number, u?: string | null) => (["umol/l", "µmol/l", "micromol/l"].includes((u ?? "mg/dl").toLowerCase()) ? v / 88.42 : v);
const r1 = (x: number) => Math.round(x * 10) / 10;
const r2 = (x: number) => Math.round(x * 100) / 100;

export function compute(
  values: Record<string, { value: number; unit: string | null }>,
  subject: { birth_year: number | null; sex: string | null } | null,
): Derived[] {
  const out: Derived[] = [];
  const g = (k: string) => values[k]?.value;
  const u = (k: string) => values[k]?.unit ?? null;
  if (g("weight") !== undefined && g("height") !== undefined) {
    const w = kg(g("weight"), u("weight")), h = cm(g("height"), u("height"));
    if (w > 0 && h > 0) {
      out.push({ key: "bmi", value: r1(w / (h / 100) ** 2), unit: "kg/m2", from: `weight ${r1(w)} kg, height ${r1(h)} cm` });
      out.push({ key: "bsa", value: r2(Math.sqrt((h * w) / 3600)), unit: "m2", from: `weight ${r1(w)} kg, height ${r1(h)} cm` });
    }
  }
  if (g("sbp") !== undefined && g("dbp") !== undefined) {
    const s = g("sbp"), d = g("dbp");
    out.push({ key: "map", value: r1(d + (s - d) / 3), unit: "mmHg", from: `systolic ${s}, diastolic ${d}` });
    out.push({ key: "pulse_pressure", value: r1(s - d), unit: "mmHg", from: `systolic ${s}, diastolic ${d}` });
  }
  if (g("qt") !== undefined && (g("rr") !== undefined || g("hr") !== undefined)) {
    const qt = ms(g("qt"), u("qt"));
    const rrS = g("rr") !== undefined ? ms(g("rr"), u("rr")) / 1000 : g("hr") > 0 ? 60 / g("hr") : 0;
    if (rrS > 0) out.push({ key: "qtcf", value: Math.round(qt / Math.cbrt(rrS)), unit: "ms", from: `QT ${qt} ms, RR ${rrS.toFixed(3)} s` });
  }
  if (g("creat") !== undefined && subject?.birth_year && (subject.sex === "Female" || subject.sex === "Male")) {
    const age = new Date().getFullYear() - subject.birth_year;
    const scr = mgdl(g("creat"), u("creat"));
    if (scr > 0 && age > 0 && age < 130) {
      const [kappa, alpha] = subject.sex === "Female" ? [0.7, -0.241] : [0.9, -0.302];
      const r = scr / kappa;
      const egfr = 142 * Math.min(r, 1) ** alpha * Math.max(r, 1) ** -1.2 * 0.9938 ** age * (subject.sex === "Female" ? 1.012 : 1);
      out.push({ key: "egfr", value: Math.round(egfr), unit: "mL/min/1.73m2", from: `creatinine ${scr} mg/dL, age ${age}, ${subject.sex.toLowerCase()}` });
    }
  }
  return out;
}
