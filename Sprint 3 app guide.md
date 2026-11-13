# eCRF Builder: a guide to the app after Sprint 3

## Instructions for Claude

I'm Jigar, one of three students who built this app for a BU Spark! project. Tomorrow I
present it to our client, Phoenix Clinical Research. I'll go through the app page by page
and ask you questions as I go.

When you answer:
- Use plain language. Explain clinical-trial words the first time they come up.
- Answer from this document. If something isn't covered here, say so. Don't guess how the
  app behaves.
- When I name a page, tell me who sees it, what it's for, and what to click to show it.
- When I ask "why", give the reason from this document. Many choices follow the client's
  own documents.
- Keep answers short unless I ask for more.

---

## 1. The app in one paragraph

A clinical trial starts with a protocol, a long PDF that describes the study. From it,
someone builds the electronic case report forms (eCRFs). These are the forms hospitals
fill in for each patient at each visit. Our app reads the protocol and drafts those forms
with an AI model. Ordinary code then checks that every field the AI proposed quotes the
protocol word for word, and deletes any field whose quote isn't found. After that the app
runs the whole data loop: hospitals enter data, the system checks it, queries go back and
forth, the sponsor approves the data, the investigator signs off, and the dashboard
reports statistics on approved data only.

**Sponsor** means Phoenix, the company running the trial. **Site** means a hospital taking
part. Sprint 1 built the pipeline from protocol to form. Sprint 2 added logins, the two
portals, patients, data entry and queries. **Sprint 3 is the hierarchy**: who can do what,
and the order data has to pass through before it counts.

## 2. What Sprint 3 added

| Area | What was added |
|---|---|
| Roles and admin | 8 roles instead of 3, a permission table, an Admin page, an access log, a forced password change on first login |
| Foundation form | A standard first form on every protocol: consent, year of birth, sex, race, ethnicity, height, weight, BMI, eligibility. Every visit also gets a Visit date field. |
| Audit trail | A comment thread on every field, a version history for the form, and a history of every change to every value |
| Data entry rules | Draft, then **Submit visit**. Answers of **Not done**, **Not applicable** or **Unknown**. A reason is required to change a value after it was submitted. |
| Edit checks | Automatic checks on entered data. The built-in checks are created when the form is locked and run on submit. A failed check raises a query from the system. Custom checks are not offered in this version. |
| The approval chain | Monitor review, data manager approval, investigator sign-off, study lock |
| Query lifecycle | Open, answered, closed or cancelled. Closing a query without a corrected value needs a reason. |
| Notifications | An inbox per person, for example "query raised", "visit submitted" or "sign-off needed" |
| Results | Results managed on the Dashboard, six fixed statistics, three dashboard tabs, a traceability matrix, a data listing with CSV export, and three PDFs (the blank eCRF, a patient casebook and the traceability matrix) |
| Client-document fixes | Ten changes made after comparing the build with Phoenix's documents (section 10) |

## 3. The hierarchy: two sides, eight roles

Each person belongs to one organisation and has one role. The organisation is either the
sponsor (Phoenix) or a site (a hospital). After signing in, sponsor staff see the
**sponsor portal** and site staff see the **site portal**. Neither side can open the
other's pages.

### Sponsor side (Phoenix)

| Role | In plain words | Demo account |
|---|---|---|
| **Admin** | Runs the system, not the study. Creates users, gives them roles and sites, sets the chain switches. Sees totals but not individual patient values. **Cannot lock a study and has no notifications.** | admin@phoenix.demo |
| **Database builder** | Builds the form. Uploads the protocol, runs the AI, edits and approves fields. **Cannot lock the form**, so the person who builds it isn't the person who freezes it. Sees no patient data. | builder@phoenix.demo |
| **Data manager** | Owns the data once the form is ready. Locks the form, assigns sites, approves values, raises and closes queries, adds and edits the results, and is **the only role who locks the study**. | dm@phoenix.demo |
| **Monitor** (also called CRA) | Checks data, but only at the sites assigned to them. Marks visits reviewed, raises and closes queries. **Cannot approve.** Sees only studies where one of their hospitals takes part. The demo monitor covers Boston General only. | cra@phoenix.demo |
| **Read only** | For an auditor. Sees protocols, the dashboard and the blank form. No buttons that change anything, and no exports. | auditor@phoenix.demo |

### Site side (hospitals)

| Role | In plain words | Demo account |
|---|---|---|
| **Investigator** (PI) | Responsible for the site's data. Views it, raises and answers queries, and is **the only role who signs off a visit**. Does **not** enter or correct data, following Phoenix's roles document. | pi@bgh.demo, pi@mrc.demo |
| **Site coordinator** (CRC) | Runs the site day to day. Registers patients, enters and submits data, answers queries, exports the site's listing. | crc@bgh.demo, crc@mrc.demo |
| **Site data entry** | Enters and submits data and answers queries. No dashboard, no listing, no PDFs. | entry@bgh.demo |

There are two demo sites: **BGH** (Boston General) and **MRC** (Mercy). In demo mode
(`./demo.sh start`) every demo account uses the password `demo1234`.

### Two layers of protection

1. **Role.** Every action needs a permission, such as `data.approve`. If your role doesn't
   have it, the server refuses the action (error 403) and the button is hidden.
2. **Scope.** Even with the permission, you only see rows in your own scope: your own
   site's patients, or a monitor's assigned sites. Anything outside your scope looks as if
   it doesn't exist (error 404), so you can't even learn it is there.
   A monitor sees only studies where one of their hospitals takes part. A study appears for
   them once one of their sites is assigned to it, and other studies give a 404.

### Who can do what

| Action | Admin | Builder | Data mgr | Monitor | Read only | Investigator | Coordinator | Data entry |
|---|---|---|---|---|---|---|---|---|
| Upload protocol, run AI, edit fields | | yes | | | | | | |
| Lock the form | | | yes | | | | | |
| Assign sites | yes | | yes | | | | | |
| Register a patient | | | | | | | yes | |
| Enter and submit data | | | | | | | yes | yes |
| Mark a visit monitor-reviewed | | | | yes | | | | |
| Approve values | | | yes | | | | | |
| Raise a query | | | yes | yes | | yes | yes | |
| Answer a query | | | | | | yes | yes | yes |
| Close a query | | | yes | yes | | | | |
| Sign off a visit | | | | | | yes | | |
| See the dashboard | yes | yes | yes | yes | yes | yes | yes | |
| See values row by row, export them | | | yes | yes | | yes | yes | |
| Add, edit or delete results | | | yes | | | | | |
| See the results, the traceability matrix and its PDF | yes | yes | yes | yes | yes | yes | yes | |
| Manage users and roles, set the chain switches | yes | | | | | | | |
| Lock the study | | | yes | | | | | |
| Have a notifications inbox | | yes | yes | yes | yes | yes | yes | yes |

## 4. The life of a study, in order

```
BUILD THE FORM          (sponsor)
  upload protocol → AI proposes visits → confirm visits → AI proposes fields
  → code checks every quote → builder reviews fields → data manager LOCKS the form
  → built-in edit checks are created → data manager assigns sites

COLLECT DATA            (site)
  coordinator registers a patient → enters the Foundation form and visits (DRAFT)
  → clicks SUBMIT VISIT → edit checks run → failed checks become system queries

CLEAN AND APPROVE       (both sides)
  queries go back and forth until closed
  → monitor marks the visit reviewed (only if that switch is on)
  → data manager APPROVES the values (blocked while a query is open on a value)
  → investigator SIGNS OFF the visit, re-entering their password (if that switch is on)

FINISH                  (sponsor)
  data manager LOCKS THE STUDY → after that, nothing in its data can change
```

### The status of a value

`draft → submitted → monitor reviewed → approved → signed off → study locked`

| Status | Meaning |
|---|---|
| Draft | The site typed it but hasn't submitted. Only that site can see it. |
| Submitted | The site submitted the visit. Edit checks ran, and the sponsor can now see it. |
| Monitor reviewed | A monitor checked the visit. This step only applies when the switch is on. |
| Approved | The data manager accepted it. **Only approved values count in statistics.** |
| Signed off | The investigator confirmed the visit. This step only applies when the switch is on. |
| Study locked | Frozen for good. |

Changing a value sends it back to **submitted**, and you have to give a reason. If its
visit was already signed, the visit now shows **Needs re-sign**. An approved value can only
change while someone on the sponsor side has a query open on it.

### The two chain switches

The admin sets these per protocol, on **Admin → Approval chain**.

| Switch | Default | When it is on |
|---|---|---|
| Monitor review required | off | The data manager can't approve until a monitor has reviewed the visit |
| Investigator signature required | on | Investigators are asked to sign, and the study can't be locked until every visit with data is signed |

### The status of a query

| Status | Meaning |
|---|---|
| Open | Raised, waiting for the other side |
| Answered | The other side replied, possibly with a corrected value. It now waits for the person who raised it. |
| Closed | Done. Closing without a corrected value needs a reason, such as "Confirmed with the site". |
| Cancelled | The person who raised it withdrew it |

A query can be about the whole study, a patient, a visit or one value. Only a query on a
value can carry a corrected value, and only the site can send one. The red badge on
**Queries** in the sidebar counts the queries waiting for *you* to act.

### Answers that aren't a value

A field can be answered **Not done**, **Not applicable** or **Unknown**, each with a reason.
If the **Visit date** is marked Not done, the visit didn't happen, so every other field in
that visit becomes Not applicable automatically. All of this is kept in the history.

## 5. Page by page

Sidebar links appear based on your role. The protocol and study links (the "protocol 1"
group) only appear once you open a protocol.

### Pages everyone has

**Login** (`/login`). One login page for everyone. The account decides which portal opens.
With a temporary password, you must change it before anything else opens
(**Change password**).

**Glossary** (link at the bottom of the sidebar). Plain-language meanings of every term on
the screens.

**Notifications** (`/notifications`). Your inbox. Every role has one except the admin. Examples: a query raised or answered, a
system query, a visit submitted or approved, sign-off needed, a sign-off that no longer
stands, the form locked, the study locked. There's one Notifications page for every study:
pick a protocol in the filter to see one study's notifications. There's no separate Study
notifications link any more.

### Sponsor portal

**Admin** (admin only). Three tabs:
- **Users**: create users, choose their role and organisation, give monitors their sites.
- **Access log**: a record of sign-ins and sensitive actions, such as switch changes and
  casebook downloads.
- **Approval chain**: the two switches, set per protocol.

The admin has no Lock study button and no Notifications link. Phoenix's roles document
puts database lock under data management, and the admin should not handle clinical data.
The server refuses both for the admin too (403), not just the screen.

**Protocols** (`/sponsor`). The list of protocols. The builder uploads a PDF here. It shows
job status while the AI runs.

**Visits** (builder). The first AI step proposes the study's visits, for example Screening,
Week 4 and Week 12. The builder corrects the list, then the app asks the AI for each
visit's fields. Checking the visits first is what cut the cost.

**Review** (all sponsor roles; only the builder can edit). Every proposed field, with its
quote from the protocol.
- Each field can be approved, flagged, rejected or edited.
- **Dropped by verification** lists the fields deleted because their quote wasn't in the
  protocol.
- Flagged fields show where a suggested unit or range came from: the protocol text, the
  CDASH library, or a guess.
- *New in Sprint 3:* comments on each field, **Version history** for the whole form, the
  Foundation form at the top, and suggested lab ranges you can accept with a click.
- The data manager locks the form here. Locking freezes that version.

**Sites** (admin and data manager). Assign hospitals to a locked form. Before the lock it
says "Lock the form first".

**Data review** (data manager, monitor). Submitted values in a table, filtered by patient,
visit and status. From here:
- The monitor marks a visit reviewed.
- The data manager ticks rows and clicks **Approve selected**. Rows with an open query
  can't be ticked.
- Anyone with the permission can raise a query.
- The data manager locks the study here, with **Lock study**. This is the only place it can be done.

**Data listing** (`/listing/<id>`; data manager, monitor, investigator, coordinator). Values
row by row, with **Export CSV**.

**Dashboard**. Three tabs:
- **Page status**: for each patient, how far each visit has got (Expected, Not started,
  Draft, Needs review, Monitor reviewed, Needs approval, Approved). Click a patient to open
  their data, or download their **Casebook** PDF. The builder, read-only and admin roles
  don't see this tab, because it is patient level.
- **Queries 360**: open, answered and closed counts, by site, with a weekly trend. The
  builder sees only queries about the form.
- **Results**: where results are managed. There's no separate Analysis plan page any more.
  - One card per result, with the app's number, the independent verifier's number, and
    PASS, FAIL or Not available.
  - The data manager sees **Add result**, and **Edit** and **Delete** on each card. The
    form asks four things: the field, the before visit, the after visit and the
    calculation. A responder rate also asks for its rule, such as "a drop of 10 or more".
    Only calculations that fit the field are offered: descriptive for numbers, frequency
    for choices and yes/no.
  - The rest is filled in for you: the SAP item name (such as "Endpoint 1"), the form, the
    unit, the endpoint/concept (editable), the derivation (such as "Week 12 value minus
    Day 1 value") and the method (such as "Paired t-test, 95% CI").
  - **Traceability matrix** opens a read-only table in the eight columns of Phoenix's
    eCRF-to-SAP guide: SAP Item, Endpoint / Concept, eCRF Form, eCRF Field(s),
    Visit / Window, Unit, Analysis Derivation, SAP Method. One row per result.
    **Download PDF** gives the same table as a PDF.
  - It also has "How the form was verified" and "Fields per visit".
- **Blank eCRF PDF** downloads the locked form, one visit per page, with each field's quote.

**Queries** (`/sponsor/queries`). Every query in scope, in tabs by status. Open one to read
the thread, answer, close (with a reason if the value didn't change) or cancel.

### Site portal

**Studies** (`/site`). The protocols this hospital is assigned to.

**Patients** (`/site/s/<id>/patients`). This site's patients, with filters for visit,
status, open queries and "needs sign-off". Status pills show each patient's state, for
example "needs sign-off" or "needs re-sign". The coordinator clicks **Register patient**,
and the system gives a code such as BGH-011. We never store a name or full date of birth.

**Data entry** (`/site/s/<id>/patients/<code>`). One patient's forms, Foundation first, then
each visit.
- Values save as **draft**. **Submit visit** first shows what the edit checks found, then
  submits.
- A value outside its range still saves, with a note. On submit it raises a query.
- Each field can be Not done, Not applicable or Unknown, with a reason.
- After submit, changing a value asks for a reason, and each value's history can be opened.
- Calculated values, such as BMI, fill themselves in and can't be typed.
- **For the investigator** the page is read only, with **Sign off this visit** (they enter
  their password again). If a value changes after signing, it shows **Needs re-sign**.
- **Casebook PDF** downloads this patient's data.

**Queries**, **Data listing**, **Dashboard** and **Notifications** work as on the sponsor
side, limited to this site.

## 6. Edit checks

An edit check tests entered data. It never changes a value.
- **Soft** (the default): the value saves, a note appears, and on submit a system query is
  raised. The query blocks approval until it's closed.
- **Hard**: the save is refused. Only format checks are hard, for example a date that isn't
  a date. That's why an out-of-range value saves and raises a query instead of being
  refused.

Built-in checks are created when the form is locked. They find their fields by CDASH code
first, then by name, so they work on any protocol. A check whose fields aren't on the form
is simply skipped.

| Code | What it asks |
|---|---|
| EC-001 | Year of birth is missing |
| EC-002 | Year of birth isn't before the year of consent |
| EC-003 | The consent date is after the first visit date |
| EC-004 | The patient is marked not eligible, but a later visit has data |
| EC-005 | Enter the visit date, or record that the visit wasn't performed |
| EC-006 | A number is outside the field's expected range |
| EC-007 | Diastolic blood pressure isn't below systolic |
| EC-008 | An adverse event's end date is before its start date |
| EC-009 | An adverse event is marked serious, with no seriousness criterion |
| EC-010 | A medication's stop date is before its start date |
| EC-011 | Not built. It needs a device or intervention form the system doesn't have. |
| EC-012 | A completion status is recorded without its date or reason |
| REQ | A required field is blank |
| FMT | A date or number field holds something else (hard) |

There's no Edit checks page. The built-in checks run automatically, and custom checks
aren't offered in this version. Nobody can switch a built-in check off.

## 7. Statistics

There are six, and no others. Nobody can type a free-form query, and that's deliberate. All
six use **approved values only**, and nothing is imputed (filled in).

| Statistic | Gives |
|---|---|
| Descriptive | n, mean, SD, median, min, max at each visit (numbers) |
| Frequency | Count and percent per category (choice, yes/no, text) |
| Change from baseline | Mean change, 95% CI, paired t-test |
| Responder rate | Share of patients whose change meets a rule (for example a drop of 10 or more), with a 95% CI |
| TEAE count | Number and percent of patients with an adverse event starting on or after their start date (treatment-emergent) |
| Percent missing | Not done and Not applicable count as missing |

A separate verification script recomputes every number without sharing any code with the
app. The Results tab shows both numbers, and **PASS** means they agree within 0.01. A grey
**Not available** is never a pass. It means there isn't enough approved data yet. Agreement
shows the code does what we intended. It doesn't show these are the right analyses for a
trial, which a statistician still needs to review.

## 8. Demo walkthrough (no AI calls, no cost)

Run `./demo.sh start` from `midterm-assets/demo`, open http://localhost:5173, and use the
password `demo1234`. The demo database starts with the sample protocol PHX-401-201 locked,
two sites assigned and 16 synthetic patients (BGH-001 to BGH-010, MRC-001 to MRC-006) whose
story shows every status, query state and notification type. `docs/demo-data.md` says which
patient to open for what. `./demo.sh reset` rebuilds it from nothing.

1. **dm@phoenix.demo**: open Review. Every field quotes the protocol, and "Dropped by
   verification" shows what was deleted.
2. **crc@bgh.demo**: go to Patients, click **Register patient**. You get BGH-011. Click
   **Enter data**.
3. Fill in the Foundation form: consent Yes, a date, version v1, born 1970, sex, race,
   ethnicity, eligible Yes. Height 150 and weight 190 give BMI 84.4, which shows a note
   because it's above 80.
4. Click **Submit visit**. The confirmation lists EC-006. Submit. One query is raised.
5. **dm@phoenix.demo**: Dashboard, Queries 360 shows Open go from 4 to 5. Go to Queries,
   close the new one on BGH-011 with "Confirmed with the site".
6. Go to Data review for BGH-011, tick all, click **Approve selected**.
7. **pi@bgh.demo**: Notifications shows "Sign-off needed". Open BGH-011. The page is read
   only. Click **Sign off this visit** and enter your password again.
8. **dm@phoenix.demo**: Dashboard, **Blank eCRF PDF**.

Why BMI 84.4 and not 52: the client's library says BMI 10 to 80 is expected, so 52 raises
nothing.

## 9. Things the client may ask about

**Built on purpose:**
- The AI is never trusted. No quote found in the protocol means no field, and the check is
  code, not another AI.
- Every review saves a new version. Nothing is overwritten, which is the audit trail.
- The builder can't lock their own form, the investigator doesn't enter data, and only the
  data manager locks the study. All three follow the client's roles document.
- Sign-off is a recorded action (who, when, password re-entered). It **isn't** presented as
  a regulated electronic signature, and we make no compliance claim.
- All data is synthetic. There's no real patient data anywhere.

**Not built yet (raised with the client):**
- Roles in their documents that we don't have: Clinical/Data Lead, Medical/Safety Reviewer,
  Sub-Investigator. Read only stands in for the Clinical/Data Lead for now.
- In the results: analysis populations, treatment groups and analysis windows.
  Results are pooled across all patients.
- Page status goes down to the patient, with a click-through. The client described each
  visit and form.
- EC-011, which needs an intervention form.

**Assumptions to confirm with them** (statistics first):
1. Results are pooled, because there are no treatment arms.
2. Repeated measurements within a visit are averaged per patient.
3. "First dosing" has no field, so the baseline visit stands in for it.
4. An out-of-range value saves and raises a query, rather than being refused.
5. Every blank required field raises its own query.
6. Locking the study also needs every value approved.
7. Sign-off is blocked by any open query on the patient, not just on that visit.

**Honest weaknesses:**
- The quote-match threshold of 90 out of 100 has never been tuned against a real answer
  key.
- The check proves a quote exists, not that it justifies the field.
- Everything from Stage 3 on was tested on the sample protocol, not a real one end to end.
- Hosting is not done yet. It runs locally. Putting it online for Phoenix to test is the
  next step.
- Accuracy against a finished Phoenix form hasn't been measured. We need one from them.

## 10. The ten fixes after reading the client's documents

1. `demo.sh` starts again when the database schema is behind.
2. The investigator views and signs, and no longer enters or corrects data.
3. The builder has no Page status or listing, and sees only queries about the form.
4. A visit date can be Not done, which makes the rest of that visit Not applicable.
5. Built-in edit checks have the owners from the spec (DM, Monitor, Site, Safety).
6. A sixth statistic, frequency, for categorical fields.
7. The traceability matrix has the client's eight columns. (Since then, the results moved onto the
   Dashboard and the matrix became a generated table and PDF.)
8. The site completion guide follows the client's template.
9. The demo script matches the build.
10. The sprint report was updated.

## 11. Words you'll see

| Word | Meaning |
|---|---|
| Protocol | The PDF that describes the study |
| eCRF | Electronic case report form: the form a site fills in |
| Sponsor | The company running the trial (Phoenix) |
| Site | A hospital taking part |
| Subject | A patient in the trial, known only by a code |
| Visit | A scheduled appointment, for example Screening or Week 4 |
| CDASH | A standard set of field names and codes for clinical data |
| Query | A question about data, sent between sponsor and site |
| Edit check | An automatic rule run on entered data |
| SAP | Statistical analysis plan: what will be analysed and how |
| Baseline | The starting measurement that later values are compared with |
| TEAE | Treatment-emergent adverse event: a side effect starting after treatment began |
| Casebook | All of one patient's data as a PDF |
| CRA | Clinical research associate, the monitor role |
| PI | Principal investigator, the doctor responsible at a site |
| CRC | Clinical research coordinator, who runs a site day to day |
