# Roles and permissions

There are eight roles, five on the sponsor side and three on the site side. A person
has one role and belongs to one organisation. The matrix lives in
`backend/ecrf/auth/permissions.py`, and `tests/test_permissions.py` asserts it cell by
cell.

## The matrix

| Permission | Means | Admin | Builder | Data mgr | Monitor | Read only | Investigator | Coordinator | Data entry |
|---|---|---|---|---|---|---|---|---|---|
| `protocol.upload` | Upload a protocol |  | yes |  |  |  |  |  |  |
| `protocol.extract` | Run extraction |  | yes |  |  |  |  |  |  |
| `form.edit` | Edit and decide fields |  | yes |  |  |  |  |  |  |
| `protocol.lock` | Lock the form |  |  | yes |  |  |  |  |  |
| `protocol.view` | See protocols in scope | yes | yes | yes | yes | yes | yes | yes | yes |
| `sites.assign` | Assign sites | yes |  | yes |  |  |  |  |  |
| `subject.create` | Register a patient |  |  |  |  |  |  | yes |  |
| `data.enter` | Enter data |  |  |  |  |  | yes | yes | yes |
| `data.submit` | Submit a visit |  |  |  |  |  | yes | yes | yes |
| `data.approve` | Approve values |  |  | yes |  |  |  |  |  |
| `data.monitor_review` | Mark a visit reviewed |  |  |  | yes |  |  |  |  |
| `query.raise` | Raise a query |  |  | yes | yes |  | yes | yes |  |
| `query.answer` | Answer a query |  |  |  |  |  | yes | yes | yes |
| `query.close` | Close a query |  |  | yes | yes |  |  |  |  |
| `signoff.sign` | Investigator sign-off |  |  |  |  |  | yes |  |  |
| `dashboard.view` | See the dashboard | yes | yes | yes | yes | yes | yes | yes |  |
| `listing.view` | Read values row by row |  |  | yes | yes |  | yes | yes |  |
| `listing.export` | Export a listing |  |  | yes | yes |  | yes | yes |  |
| `report.pdf` | Download PDFs |  | yes | yes | yes | yes | yes | yes |  |
| `sap.edit` | Edit the analysis plan |  |  | yes |  |  |  |  |  |
| `users.manage` | Manage users | yes |  |  |  |  |  |  |  |
| `roles.assign` | Assign roles | yes |  |  |  |  |  |  |  |
| `chain.configure` | Set the chain switches | yes |  |  |  |  |  |  |  |
| `study.lock` | Lock the study |  |  | yes |  |  |  |  |  |
| `notifications.view` | Have a notifications inbox |  | yes | yes | yes | yes | yes | yes | yes |

Two layers decide what someone can do. `require("permission")` on each route decides
whether their role may do this at all, and gives a 403 if not. The scope helpers in
`auth/scope.py` decide whether they may see this particular row, and give a 404 if not,
so nobody can learn that a row exists.

A monitor's scope is narrower than the rest of the sponsor's. A monitor sees a protocol
only if at least one of their assigned sites (`monitor_site`) is assigned to it
(`protocol_site`), and within it only those sites' data. This covers the protocol list,
the Review page, the dashboard, queries, notifications and PDFs. Any other protocol
returns 404. A study appears for the monitor once one of their sites is assigned to it,
and disappears if that site is taken off.

Reading entered values row by row has no permission of its own. It needs `listing.view`,
`data.enter` or `data.approve`. So the admin, the builder and the read-only role see
totals but not individual values.

## The chain

Each entered value moves through these steps, and the order is fixed:

```
draft → submitted → monitor reviewed → approved → signed off → study locked
                    (if switched on)              (if switched on)
```

1. **Draft.** A site enters a value. Only that site can see it.
2. **Submitted.** The site submits the visit, and the edit checks run.
3. **Monitor reviewed.** Only if switched on. A monitor assigned to the site marks the visit reviewed.
4. **Approved.** The data manager approves values. An open query on a value blocks this.
5. **Signed off.** Only if switched on. The investigator confirms the visit, entering their password again. This needs every value at the visit approved and no query open on the patient.
6. **Study locked.** The data manager locks the study. This needs a locked form, no open queries, every value approved and, if sign-off is on, every visit with data signed. After this, every write to the study's data is refused.

Changing a value sends it back to submitted, with a reason. If its visit was signed, the
sign-off no longer stands, and the visit shows **Needs re-sign**. An approved value can
change only while a person on the sponsor side has a query open on it.

Investigator sign-off is a recorded action: who, when, what it means, and a password
entered again. It is not presented as an electronic signature under any regulation, and
this prototype makes no compliance claim.

## The two switches

Set per protocol by the admin, on **Admin**, **Approval chain**. Each change is on the access log.

| Switch | Default | When on |
|---|---|---|
| `monitor_review_required` | off | The data manager cannot approve a value until a monitor has reviewed its visit |
| `investigator_signature_required` | on | Investigators are asked to sign, and the study lock needs every visit with data signed |

## Each role in plain language

**Admin.** Runs the system, not the study: creates users, assigns roles and sites, and
sets the chain switches. Sees the dashboard's totals, but not individual values, and
cannot approve data or edit a form. Cannot lock a study and has no notifications:
Phoenix's roles document puts database lock under data management, and the admin should
not handle clinical data. The server refuses both with 403, and no notification is ever
written for an admin.

**Database builder.** Turns a protocol into a form: uploads it, runs extraction, and
edits, approves or rejects fields. Cannot lock the form, so the person who builds it is
not the person who freezes it. Sees no individual values.

**Data manager.** Owns the data once the form is ready: locks the form, assigns sites,
approves values, raises and closes queries, edits the analysis plan and locks the study.

**Monitor.** Checks data at the sites assigned to them and nowhere else: reviews visits,
raises and closes queries, reads and exports listings. Cannot approve data. Sees only
studies where one of their hospitals takes part.

**Read only.** Sees protocols, the dashboard and the blank eCRF, with no write button
anywhere. For an auditor. Sees totals rather than individual values, and cannot export.

**Investigator.** Responsible for a site's data: enters, submits, raises and answers
queries, and is the only role who can sign off a visit. Cannot register a patient.

**Site coordinator.** Runs the site's day to day: registers patients, enters and submits
data, raises and answers queries, reads and exports the site's listings. Cannot sign off.

**Site data entry.** Enters and submits data and answers queries. Sees no dashboard,
listing or PDFs.

## Choices made where the matrix was silent

- A site's own question needs someone to answer it, and the matrix gives sponsor roles no
  `query.answer`. So whoever holds `query.close` may reply in words to a query a site raised.
- A casebook needs `listing.view`, not only `report.pdf`, because it shows values row by
  row. The read-only role and the builder can get the blank eCRF but not a casebook.
- Loading synthetic data needs `data.approve`.
- Reviewer comments can be written by the builder and data manager, and read by sponsor
  roles. Sites do not see them.
