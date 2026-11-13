# Demo script

Walks the build from a locked form to a signed visit and a PDF. Every step below was run in a
browser on a freshly built demo database. It extracts nothing, so it makes no model calls.

`Demo script.pdf` in the main folder is the older midterm recording script, with a live paid
extraction of a different protocol. It does not match this build: for one, its "HbA1c of 13?
Refused" step no longer happens.

## Before you start

```bash
cd midterm-assets/demo
./demo.sh start
```

Open <http://localhost:5173>. The login page lists the ten accounts, and clicking one fills in
the form. The password for all of them is `demo1234`. Run `./demo.sh start` again before each
retake, and `./demo.sh stop` to go back to your normal data.

The database starts with the synthetic sample PHX-401-201 locked, Boston General and Mercy
assigned, and 16 synthetic patients (BGH-001 to BGH-010, MRC-001 to MRC-006) whose story
shows every status, query state and notification type. `docs/demo-data.md` says which patient
to open for what.

## The steps

**1. The form proves itself.** Sign in as `dm@phoenix.demo`. Open `/sponsor/p/1/review`.

- Every field quotes the protocol.
- **Dropped by verification** shows what the quote check deleted.

**2. A site registers a patient.** Sign in as `crc@bgh.demo`. Open the study with **Patients**
(`/site/s/1/patients`). Click **Register patient**, then **Register**. The system assigns
BGH-011, never a name. Click **Enter data** on its row.

**3. Enter the Foundation form.** Consent Yes, a consent date, version `v1`, year of birth `1970`,
then sex, race and ethnicity, and Eligible Yes. Enter height `150` and weight `190`.

- BMI fills in as 84.4, and the note says "above 80: this will raise a query on submit".
- The value still saves. Nothing is refused for being out of range.

**4. Submit.** Click **Submit visit**. The confirmation lists "EC-006 BMI is outside the expected
range 10 to 80". Click **Submit visit** again. The screen says "12 values submitted for
Foundation. 1 query raised."

**5. The sponsor sees the query.** Sign in as `dm@phoenix.demo`. Open `/sponsor/p/1/dashboard`.
**Queries 360** shows Open go from 4 to 5. Open **Queries** (`/sponsor/queries`) and the **open** tab: the query
says who raised it (an edit check) and which value. The value has not changed, so closing asks
why. Type `Confirmed with the site` and click **Close query**.

**6. Approve.** Open `/sponsor/p/1/data?subject=BGH-011`. Tick the box at the top of the table and
click **Approve selected**. The screen says "12 values approved".

**7. Investigator sign-off.** Sign in as `pi@bgh.demo`. **Notifications** (`/notifications`) has
"Sign-off needed" at the top. Open `/site/s/1/patients/BGH-011`: the page is read only, because
an investigator reviews and does not enter data. Click **Sign off this visit**, enter the password
again and click **Sign**. The page shows who signed and when.

**8. The blank eCRF.** Sign in as `dm@phoenix.demo`. On `/sponsor/p/1/dashboard`, click **Blank eCRF
PDF**. The locked form downloads, one visit to a new page, with each field's protocol quote.

## Why BMI 84.4 and not 52

The client's library sets BMI's expected range at 10 to 80. A BMI of 52 is inside it, so it saves
and raises nothing: the confirmation says "Every check passes". To show EC-006, the value has to be
outside the range. Height 150 and weight 190 give 84.4.

BMI is calculated, so it cannot be typed. Change the height or weight to change it.
