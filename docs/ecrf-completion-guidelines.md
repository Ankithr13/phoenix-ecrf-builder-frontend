# eCRF completion guidelines

**Draft for Denise to edit.** It follows the headings of the client's template and
describes how this system behaves today. Study-specific rules still need adding.

## Purpose

This guide tells site staff how to enter, correct and confirm a patient's data in
the eCRF Builder. All data in this prototype is synthetic. Do not enter real
patient information.

## Core expectations

- Enter data from the source record, at or soon after the visit.
- Identify a patient only by the code the system gives at registration. Never enter
  a name, initials, full date of birth or contact details, in any field or note.
- Your own sign-in is yours. Do not share it.
- Every change after submission is recorded with who, when, the old value, the new
  value and your reason.

## Who does what

| Role | Registers patients | Enters and submits | Answers queries | Signs off |
|---|---|---|---|---|
| Site coordinator | yes | yes | yes | no |
| Site data entry | no | yes | yes | no |
| Investigator | no | yes | yes | yes |

## Field rules

- **Saving.** Values save as you move between fields, as drafts only your site can
  see, until you submit the visit.
- **Dates.** Use the date picker. Dates are stored as year, month, day.
- **Numbers.** The field shows its unit and expected range. A value outside the range
  still saves and raises a query on submit, so if it is correct, keep it and say so
  when asked. A value in the wrong format will not save.
- **Calculated fields.** BMI, age at consent and similar fields fill in from what you
  entered. Correct the inputs rather than the result.
- **Repeated readings.** Enter each reading in its own box.
- **No value to give.** Where a field allows it, choose Not done, Not applicable or
  Unknown, and give the reason. Do not type "N/A" or leave a required field blank
  on purpose: a blank raises a query.
- **Changing a submitted value.** The system asks for a reason, and the value goes
  back for review.
- **Changing an approved value.** This is possible only while the sponsor has a query
  open on it. Until then the value is frozen.

## Form by form

- **Foundation.** The first form for every patient: consent, year of birth, age at
  consent, sex, race, ethnicity, height, weight, BMI and eligibility.
- **Each visit.** Opens with the visit date, then the fields the protocol requires
  for that visit. Under each field are its unit and range. Fill the visit date first:
  several checks depend on it.
- **Adverse events.** Record the start date wherever the form asks. It decides whether
  the event counts as treatment-emergent.

*To add: study-specific instructions for each form.*

## Queries

A query is a question about a value, a visit or a patient. It may come from the
sponsor or from an edit check, and you can raise one yourself.

1. Open **Queries**. The **My turn** tab shows what needs you.
2. Answer in words, and correct the value there if it was wrong.
3. The sponsor closes the query once it is settled. Only the sponsor can close one.

If a check raised the query and you fix the value, the system answers it for you.

## Investigator sign-off

Once every value at a visit is approved and no query is open on the patient, the
investigator is notified. To sign off, open the visit, read the statement, enter your
password again and confirm:

> I confirm this visit's data is complete and accurate to the best of my knowledge

If a value changes afterwards, that sign-off no longer stands. The visit shows
**Needs re-sign**, and the investigator is notified.

This is a recorded action in this prototype. It makes no claim to meet any regulation
on electronic signatures.

## Pre-lock checklist

Before a study can be locked:

- [ ] Every visit that was started has been submitted.
- [ ] Every entered value has been approved.
- [ ] No query is open or waiting to be closed.
- [ ] Every visit with data has a valid investigator sign-off, if the study requires one.

The **Data review** page lists whatever is still in the way. After the study lock, no
data on the study can change.
