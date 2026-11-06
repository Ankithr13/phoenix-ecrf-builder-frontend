# The statistical analysis plan page

The **Analysis plan** page (`/sponsor/p/<id>/sap`) is a table with one row per thing
to analyse. The data manager edits it. Everyone else with dashboard access can read
it. A row only points the fixed calculations at a field: nothing on the page can add
a new calculation.

## How it maps to the client's traceability matrix

| Client's matrix | Column on the page | Stored as |
|---|---|---|
| Endpoint | Label | `sap_item.label` |
| Type of objective | Kind: endpoint, safety, disposition or baseline | `kind` |
| Form and field | Field | `field_id`, the field's stable id. It survives a rename. |
| Visit | Baseline visit, Analysis visit | `baseline_visit_id`, `analysis_visit_id`, which hold the visit's name |
| Unit | Unit | `unit`, filled from the field when you pick it |
| Derivation | Responder rule. Change from baseline is built in. | `responder_rule`, such as `{"on": "change", "op": "<=", "value": -10}` |
| Method | Method | `method`, free text shown with the result. It describes and does not choose the calculation. |

Each change to a row writes `form_field_history`.

## What each kind computes

| Kind | Needs | Computes |
|---|---|---|
| Endpoint | Numeric field, baseline and analysis visits that differ | Descriptive, change from baseline, responder rate if a rule is set, percent missing |
| Baseline | Baseline visit | Descriptive at that visit, percent missing |
| Disposition | Analysis visit | Descriptive at that visit if the field is numeric, percent missing |
| Safety | The adverse event's start date field | TEAE count, percent missing |

## The statistics that exist

These five, and no others. Anything else raises `UnsupportedAnalysis`.

All of them read approved values only, and repeats within a visit are averaged per
subject first. Nothing is imputed.

| Name | Result | Rule |
|---|---|---|
| `descriptive` | n, mean, SD, median, min, max at each visit | SD needs two subjects, and is blank with one |
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

## What the plan cannot express

The client's SAP guide covers these. This system does not have them, so a real analysis
still needs a statistician and the SAP itself:

- **Treatment arms.** Results are pooled. There is no arm or randomisation data, so
  there is no comparison between arms.
- **Analysis populations**, such as intention to treat or per protocol.
- **Missing-data methods.** Subjects without a value are left out, and that is all.
- **Other models**, such as ANCOVA or survival analysis.
- **A first-dosing field.** A safety row's baseline visit stands in for it.
