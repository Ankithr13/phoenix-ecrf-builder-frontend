# eCRF Completion Guidelines

**Draft for Phoenix to edit.** Site-facing instructions for accurate and consistent eCRF
entry in the eCRF Builder.

| | | | |
|---|---|---|---|
| Protocol: | | Version: | |
| Effective Date: | | Prepared by: | |
| EDC System: | | Approved by: | |

## 1. Purpose

These guidelines explain how to enter, correct and confirm study data in this system. Use
them with the protocol and your site's procedures. All data in this prototype is synthetic,
so do not enter real patient information.

## 2. Core Data Entry Expectations

- Enter data from source records, at or soon after the visit. Do not guess, infer or back-fill.
- Identify a patient only by the code the system assigned. Never enter a name, initials or
  contact details in any field or note.
- Site coordinators and data entry staff enter and submit data. Investigators review it and
  answer queries in words, and do not enter it.
- Values save as you move between fields, as drafts only your site can see, until you submit
  the visit. Every later change records who, when, the old value, the new value and your reason.

## 3. General Field Completion Rules

| Data type | What to do here |
|---|---|
| Dates | Use the date picker. Partial dates are not supported, so use Unknown or Not done where offered. |
| Times | This system has no time fields. |
| Numeric values | Enter the source value in the unit shown. A value outside the expected range still saves and raises a query on submit; if it is right, keep it and say so. A value in the wrong format will not save. Calculated fields such as BMI fill in from their inputs, so correct the inputs. |
| Text fields | Concise and factual, with no identifiers. |
| Yes/No fields | Choose Yes or No. Not answered does not mean No. Complete dependent fields. |
| Not Done / Not Applicable | Only where the field offers them, each with a reason. |
| Unknown | Only where the field offers it, and it is genuinely unknown, with a reason. |
| Corrections | The system asks for a reason on a submitted value, and it goes back for review. An approved value can change only while the sponsor has a query open on it. |

## 4. Form-by-Form Guide

| Form | What to enter | Key note |
|---|---|---|
| Subject Identification | Nothing to type. A site coordinator registers the patient and the system assigns the code. | No names or initials. |
| Informed Consent | On the Foundation form: consent obtained, consent date and version. | The consent date must not be after the first visit date. |
| Demographics | On the Foundation form: year of birth, sex, race, ethnicity, height, weight. | Age and BMI are calculated. Full date of birth is not collected in this system. |
| Eligibility | On the Foundation form: one Eligible answer, yes or no. | Criterion-by-criterion eligibility is not collected in this system. A later visit with data raises a query if the answer is No. |
| Visit Forms | The visit date first, then the fields the protocol requires for that visit. | If the visit did not happen, mark the visit date Not done with a reason. Every other field at that visit becomes Not applicable. |
| Medical History | Not collected in this system as a standard form. | Appears only if the protocol's form includes it. |
| Concomitant Medications | Not collected in this system as a standard form. | Where the protocol's form includes it, a stop date before a start date raises a query. |
| Adverse Events | The fields on the protocol's form. | The start date decides whether an event counts as treatment-emergent. Entry here does not replace separate safety reporting. |
| Study Completion | Not collected in this system as a standard form. | Where the protocol's form includes it, a status without its date or reason raises a query. |

## 5. Queries

A query may come from the sponsor or an edit check, and you can raise one yourself. Open
**Queries**; the **my turn** tab shows what needs you. Review the source record. If the eCRF is
wrong, correct it. If it is right, say so briefly. Do not change accurate data just to clear a
query. Only the sponsor closes a query. If a check raised it and you fix the value, the system
answers it for you.

## 6. Investigator Review and Sign-off

When every value at a visit is approved and no query is open on the patient, the investigator
is notified. They open the visit, read the statement, enter their password again and confirm:

> I confirm this visit's data is complete and accurate to the best of my knowledge

If a value changes afterwards, that sign-off no longer stands. The visit shows **Needs re-sign**
and the investigator is notified. Whether a study needs this is set per protocol.

## 7. Pre-Lock Site Checklist

- [ ] All expected visits and forms are present, or documented as not performed or not applicable.
- [ ] Required fields are complete.
- [ ] Open queries have been addressed.
- [ ] Key dates are internally consistent.
- [ ] Adverse event and concomitant medication data are reconciled as required.
- [ ] Protocol deviations are documented in the study records. This system has no deviation form.
- [ ] Required investigator review and sign-off is complete.

The sponsor's **Data review** page lists what still blocks the study lock. After that lock, no
data on the study can change.

## 8. Training Acknowledgment

| Name | Role | Signature | Date |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
