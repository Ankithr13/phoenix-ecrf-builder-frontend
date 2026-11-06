# Edit checks

An edit check tests entered data and either asks a question or stops a save. A
check is a row in the `edit_check` table with a type and a little JSON, not code.
It never changes a value. The data stays as the site entered it.

The evaluators are in `backend/ecrf/checks/engine.py`, the built-in list in
`checks/builtin.py`, and the code that raises queries in `checks/run.py`.

## Soft and hard

- **Soft** is the default. The value saves, a note appears next to the field, and
  on submit the failure becomes a query from the system. A query does not change
  the value's status, but it blocks approval until it is closed.
- **Hard** stops the save. Only `format` checks can be hard, because a value in
  the wrong format cannot be stored as what the field says it is. Every other
  question about a value is one a person may need to answer, so it stays soft.

A value out of its expected range therefore saves and raises a query. It is not
refused.

## The types

| Type | Fails when | Logic |
|---|---|---|
| `required` | A required field is blank. An answer of Not done, Not applicable or Unknown counts as answered. | none |
| `range` | A number is outside a minimum or maximum. | `min`, `max` |
| `format` | A value is not a valid date, integer or decimal, or does not match a pattern. | `kind`, `pattern`, `max_decimals` |
| `cross_field` | Two values on one visit fail a comparison. | `a`, `b`, `op` |
| `cross_form` | Two values on different visits fail a comparison. | `a`, `b`, `op` |
| `temporal` | Two dates are in the wrong order. | `a`, `b`, `op`, `granularity` |
| `conditional` | If one field has a value, something else must hold. | `if_field`, `equals`, `then_required`, `then_any`, `then_no_later_data` |

There is also `manual`: a check for people to do. It is listed and never run.

A check passes when the values it needs are not there yet. Only `required` exists
to notice a blank.

## Built-in checks

Generated when the form is locked. They find their fields by CDASH code first and
by name second, so they work on any protocol. A check whose fields are not on the
form is simply not created.

| Code | Type | What it asks |
|---|---|---|
| EC-001 | `required` | Year of birth is missing. |
| EC-002 | `temporal` | Year of birth is not before the year of consent. |
| EC-003 | `temporal` | The consent date is after the first visit date. |
| EC-004 | `conditional` | The patient is marked not eligible, but a later visit has data. |
| EC-005 | `required` | A visit's date is missing. |
| EC-006 | `range` | A number is outside the field's expected range. |
| EC-007 | `cross_field` | Diastolic blood pressure is not below systolic. |
| EC-008 | `temporal` | An adverse event's end date is before its start date. |
| EC-009 | `conditional` | An adverse event is marked serious with no seriousness criterion. |
| EC-010 | `temporal` | A medication's stop date is before its start date. |
| EC-011 | | Not built. It needs an intervention form this system does not model. |
| EC-012 | `conditional` | A completion status is recorded without its date or reason. |
| REQ | `required` | A required field not already covered above is blank. |
| FMT | `format`, hard | A date, integer or decimal field holds something else. |

A built-in format check stays on, because it follows from the field's type. Other
built-in checks can be switched off.

## When they run

- **While typing:** a soft failure shows as a note next to the field.
- **Before submitting:** the confirmation lists what would be queried.
- **On submit:** each new failure raises one query from the system. A value edited
  after submission runs the checks again.

Once raised:

- A failure with a live query does not raise a second one.
- When the value is fixed, the system answers its own query, and the sponsor closes it.
- When a person closes a system query, it stays closed until the value it is about
  changes. Otherwise every later edit on the visit would ask the same thing again.

## Adding a custom check

On the **Edit checks** page: pick a type, the fields and the message the site will
see, and try it against sample values before saving.

- Before the form is locked, the database builder manages checks.
- After the lock, only the data manager can, because a change can affect data
  already entered. Each change writes a row to `form_field_history`.

Custom checks get the codes `CUSTOM-1`, `CUSTOM-2` and so on. There is no generic
rules language: a custom check is one of the types above.
