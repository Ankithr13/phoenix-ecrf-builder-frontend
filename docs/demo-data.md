# Demo data: which patient shows what

`./demo.sh start` (or `./demo.sh reset`) in `midterm-assets/demo` builds this. It
contains PHX-401-201 with its form locked, Boston General (BGH) and Mercy (MRC)
assigned, and 16 synthetic patients. Their story runs over the 28 days before the
build. Every step went through the real API as the right account. The password
is `demo1234` for every account. Baseline is **Day 1** and the final visit is
**Week 12**. Foundation, Screening and Week 4 are filled in too. Early Termination
is empty, because nobody withdraws. BGH-011 is left free for the live walkthrough.

Pages: Data review is `/sponsor/p/1/data?subject=CODE` (dm, cra). A patient page
is `/site/s/1/patients/CODE` (crc, pi). The Dashboard has the Results and
Queries 360 tabs.

## 1. The patients

| Code | Story | Open | What the audience sees |
|---|---|---|---|
| BGH-001, 002, 003 | Every visit submitted, approved and signed. BGH-002 has a Week 4 AE (Headache) | Patient page as pi@bgh | A finished patient: all Approved, each visit signed |
| BGH-004 | All approved. Week 12 not signed | pi@bgh: Notifications, then BGH-004 | "Needs sign-off" on Week 12, and a "ready for your sign-off" notification |
| BGH-005 | All signed. The monitor queried Week 12 weight. The coordinator corrected 98.4 to 96 with a reason, the DM closed the query and re-approved | Patient page as pi@bgh. Then Data review, Week 12 weight, history | "Needs re-sign" on Week 12. History shows 98.4 → 96 with the query as the reason. A "sign-off no longer stands" notification |
| BGH-006 | Earlier visits signed. Week 12 systolic readings are 260, 151 and 150 | Queries as dm, or Data review | An **open EC-006 system query**. Week 12 can't be approved. Also an open **visit-level** query: "Please confirm the BP cuff size used." |
| BGH-007 | DM queried Day 1 diastolic 58. The coordinator answered "Transcription error" and corrected it to 85 | Queries as dm | An **answered** query waiting for the DM. Day 1 diastolic history shows 58 → 85 |
| BGH-008 | DM queried Week 12 weight (61.4). The coordinator answered "Value confirmed in source record" with no change. Closed "Confirmed with the site", then approved and signed. Week 4 AE (Dizziness) | Queries, filter Closed | A **closed** query with no change and a close reason |
| BGH-009 | DM raised a patient query, then cancelled it: "Raised on the wrong patient" | Queries, filter Cancelled | A **cancelled** query |
| BGH-010 | Day 1 approved. Week 4 visit date Not done, "Patient travelling", rest Not applicable. Week 12 typed but not submitted. Open **patient-level** query: "Please confirm whether the missed visit will be rescheduled." | Patient page as crc@bgh. Then Results | 14 **draft** values only the site sees, a missed visit, and systolic missing at 9.4% |
| MRC-001 to 004 | Every visit approved and signed by pi@mrc. MRC-003 has a Week 4 AE (Nausea) | Data review as dm, site MRC | Finished, second site |
| MRC-005 | Earlier visits signed. Week 12 systolic 140, diastolic 150 | Queries as dm or crc@mrc | An **open EC-007 system query**: diastolic not below systolic |
| MRC-006 | Finished. The Mercy coordinator asked a **study-level** question: "Is the Week 12 visit window plus or minus 3 days?" DM: "Plus or minus 7 days, see protocol section 6." | Queries as crc@mrc | A query going **from the site to Phoenix**, answered |

## 2. Unread notifications

| Account | Unread | Read |
|---|---|---|
| dm@phoenix.demo | 79 | 3 |
| cra@phoenix.demo | 50 | 0 |
| pi@bgh.demo | 57 | 0 |
| pi@mrc.demo | 31 | 0 |
| crc@bgh.demo | 54 | 2 |
| crc@mrc.demo | 32 | 0 |
| entry@bgh.demo | 56 | 0 |

The counts are high because every submit and every approval notifies.

## 3. Queries

| Status | Count |
|---|---|
| Open | 4: EC-006 on BGH-006, EC-007 on MRC-005, the BGH-006 visit query, the BGH-010 patient query |
| Answered | 2: BGH-007, MRC-006 |
| Closed | 2: BGH-005, BGH-008 |
| Cancelled | 1: BGH-009 |

Queries 360 has three weekly points, from the weeks of 26 October, 2 November and 9 November.

## 4. Results (Dashboard, Results tab)

Every card is **PASS**: the app and the independent script agree.

| Result | Value | Missing |
|---|---|---|
| Baseline 1: weight at Day 1, descriptive | n 16, mean 69.8 kg, SD 14.6, median 64.7, range 55.3 to 98.1 | 0% |
| Baseline 2: sex at Foundation, frequency | M 8 (50%), F 8 (50%) | 0% |
| Endpoint 1: systolic, change Day 1 to Week 12 | n 13, mean −11.0 mmHg, 95% CI −13.8 to −8.1, p < 0.001 | 9.4% (87 of 96) |
| Endpoint 2: systolic responders, drop of 10 or more | 6 of 13, 46.2%, 95% CI 23.2% to 70.9% | 9.4% |
| Safety 1: AE start date, TEAE count after Day 1 | 3 of 16 patients, 18.8% | 90.6%. The AE date is blank when there is no AE |

## 5. Changed or skipped, and why

- **Visits.** The form's first visit is Foundation, which has no blood pressure, and its last is Early Termination. So baseline is Day 1 and final is Week 12.
- **No full dates of birth.** The Screening form had a required Date of Birth field. The builder rejects it at review, before the lock. Foundation's Year of birth stays.
- **No heart rate field.** BGH-007's query is on Day 1 diastolic instead, 58 corrected to 85.
- **Systolic 210 raises nothing.** EC-006's range is 60 to 250, so BGH-006 has a 260 reading.
- **Percent missing is not a result of its own.** It comes with every card, so the plan has five results, not six.
- **Sex frequency is at Foundation,** because sex is not collected at Day 1. Only M and F are used, because Screening's sex offers only Male and Female.
- **Mercy investigator.** `pi@mrc.demo` was added as a tenth demo account so Mercy visits can be signed.
- **No "study locked" notification.** Locking the study freezes all data, including the live walkthrough. The other eight notification types are all present.
- **Blood pressure is taken three times a visit.** All three readings are entered. A story's value is the first reading.
- **Dates move with the build day.** All numbers are fixed by a random seed. Visit dates and timestamps are counted back from the build date, so `--as-of YYYY-MM-DD` reproduces a build exactly.
