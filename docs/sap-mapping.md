# Results and the traceability matrix

**Results are managed on the Dashboard**, in the Results tab. There is no separate
Analysis plan page. Each result is one `sap_item` row and one card, showing the app's
value, the independent verifier's value and PASS, FAIL or Not available.

The data manager adds, edits and deletes results (`sap.edit`). Every other role that
sees the dashboard sees the cards and the matrix and can download the PDF. Site data
entry sees no dashboard. A result only points the fixed calculations at a field:
nothing on the page can add a new calculation.

## Adding a result

**Add result** asks for four things:

1. **Field**
2. **Before visit** (baseline)
3. **After visit** (analysis)
4. **Calculation**: only the ones that fit the field are offered

A responder rate also takes its rule, such as "a drop of 10 or more", which is stored as
`{"on": "change", "op": "<=", "value": -10}`.

| Calculation | Field | Visits | Stored as kind |
|---|---|---|---|
| Descriptive statistics | numeric | one: before or after | `baseline` (before) or `disposition` (after) |
| Frequency | choice, yes/no or text | one: before or after | `baseline` or `disposition` |
| Change from baseline | numeric | both, different | `endpoint` |
| Responder rate | numeric | both, plus the rule | `endpoint` with `responder_rule` |
| Treatment-emergent adverse events | the AE start date | before visit optional, as the start of treatment | `safety` |

Missing values come with every result and are not a choice. The kind is what the
registry and the verifier read, so neither changed.

The server fills in and stores the rest:

| Column | Filled with |
|---|---|
| `label` (SAP Item) | The kind and a number, such as "Endpoint 1". Kept on edit. |
| `endpoint_concept` | "<field name> <calculation>", such as "Systolic Blood Pressure change from baseline". Editable. |
| `form` | The forms holding the field at the chosen visits |
| `unit` | The field's unit |
| `derivation` | In words, such as "Week 12 value minus Screening value, paired by subject" |
| `method` | From the calculation, such as "Paired t-test, 95% CI" |

Rows made before this have null `form` and `derivation`, and the API works both out
from the form instead. Each change to a row writes `form_field_history`.

## The traceability matrix

**Traceability matrix** on the Results tab opens a read-only table, generated from the
results, in the eight columns of section 3 of Phoenix's eCRF-to-SAP guide, in its order:

| Column | From |
|---|---|
| SAP Item | `label` |
| Endpoint / Concept | `endpoint_concept` |
| eCRF Form | `form` |
| eCRF Field(s) | the field named by `field_id`, the stable id that survives a rename. One field per row. |
| Visit / Window | `baseline_visit_id` → `analysis_visit_id`. Visits, not windows. |
| Unit | `unit` |
| Analysis Derivation | `derivation` |
| SAP Method | `method` |

**Download PDF** gets `GET /api/protocols/{id}/pdf/traceability`: the same table,
landscape, in the blank eCRF's style, with the protocol and form version in the header.
`GET /api/protocols/{id}/traceability` returns it as JSON. Both are scoped like the
dashboard.

## What each kind computes

| Kind | Needs | Computes |
|---|---|---|
| Endpoint | Numeric field, baseline and analysis visits that differ | Descriptive, change from baseline, responder rate if a rule is set, percent missing |
| Baseline | Baseline visit; a numeric or categorical field | Descriptive at that visit if numeric, frequency if categorical, percent missing |
| Disposition | Analysis visit; a numeric or categorical field | Descriptive at that visit if numeric, frequency if categorical, percent missing |
| Safety | The adverse event's start date field | TEAE count, percent missing |

## The statistics that exist

These six, and no others. Anything else raises `UnsupportedAnalysis`.

All of them read approved values only, and repeats within a visit are averaged per
subject first. Nothing is imputed.

| Name | Result | Rule |
|---|---|---|
| `descriptive` | n, mean, SD, median, min, max at each visit | For a numeric field. A categorical one is refused. SD needs two subjects, and is blank with one |
| `frequency` | n, missing, count and percent per category | For a choice, yes/no or status field, at the baseline visit for a baseline item and the analysis visit otherwise. Percent is of n, the subjects with an approved answer. Missing is reported separately. A numeric field is refused. |
| `change_from_baseline` | n, mean, SD, 95% CI, t, p | Analysis minus baseline, paired by subject. Subjects without both values are left out, never counted as no change. CI from the t distribution, p from a paired t-test. Needs two pairs. |
| `responder_rate` | responders, n, rate, Wilson 95% CI | Subjects meeting the rule, out of those with both values |
| `teae_count` | subjects, denominator, percent | Subjects with an AE starting on or after their start date. The start is the date at the row's baseline visit if set, otherwise the subject's first visit date. The denominator is subjects with such a date. |
| `percent_missing` | percent, expected, present | Expected is the form's slots for this field at these visits, times registered subjects. Present is slots holding an approved value. Not done and Not applicable count as missing. |

## How the numbers are checked

`backend/verification/expected_results.py` recomputes every result from raw SQL with
the `statistics` module and `scipy.stats`, and imports nothing from `ecrf/`. It works
out what a row means from the stored form itself. The **Results** tab shows both
numbers, and PASS needs them within 0.01 of each other.

"Not available" is grey and is never a pass. It means there was not enough approved
data, or the field is no longer on the form.

Agreement between the two shows the code does what was intended. It does not show
that this analysis suits the trial: that is the statistician's call.

## Who sees what

Site roles see their own site's numbers, and a monitor sees assigned sites. Both the
app and the verifier apply that limit. The data manager, builder, admin and read-only
roles see the whole study.

## What results cannot express

The client's SAP guide covers these. This system does not have them, so a real analysis
still needs a statistician and the SAP itself:

- **Treatment arms.** Results are pooled. There is no arm or randomisation data, so
  there is no comparison between arms.
- **Analysis populations**, such as intention to treat or per protocol.
- **Missing-data methods.** Subjects without a value are left out, and that is all.
- **Other models**, such as ANCOVA or survival analysis.
- **A first-dosing field.** A safety row's baseline visit stands in for it.
