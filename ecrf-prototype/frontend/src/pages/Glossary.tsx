import { useAuth } from "../auth/useAuth";

/* Every word the screens use, in plain language, with an example. Reached
   from the bottom of the sidebar on both portals. */

interface Term { word: string; means: string; example?: string }
interface Group { title: string; terms: Term[] }

const GROUPS: Group[] = [
  {
    title: "A field and where it comes from",
    terms: [
      { word: "Field", means: "One box on the form a site will fill in: a name, a type (number, text, date, yes/no, choice), and for numbers a unit and an allowed range.",
        example: "Systolic Blood Pressure · integer · mmHg · 60 to 260" },
      { word: "Quote and §section", means: "The sentence in the protocol that asks for this field, copied word for word by the model. Click § to read that part of the protocol.",
        example: "\"Vital signs will include blood pressure (systolic and diastolic), heart rate…\"" },
      { word: "Match score", means: "How well the quote was found in the protocol text. 100 means word for word. Below 90 the field is deleted before anyone sees it, because a quote that cannot be found is the sign of an invented field." },
      { word: "Dropped by verification", means: "Fields the model proposed whose quote was not found, or whose answer was malformed. Listed on the Review page so the check can be seen working; nobody approves them." },
    ],
  },
  {
    title: "The status of a field",
    terms: [
      { word: "Draft", means: "The quote was found and the model saw nothing missing. Plausible and grounded, but a person still has to say yes or no.",
        example: "Weight · kg · the protocol states both, so there is nothing to question." },
      { word: "Flagged", means: "The quote was found, but the model says the protocol left something out or is unclear: missing (no unit or range), ambiguous, conflicting, or unsupported (the model inferred a field the protocol never defines). The yellow note says what.",
        example: "Heart Rate · the protocol says to measure it but gives no unit or range." },
      { word: "Approved", means: "A person signed it off. Only approved fields appear on the form sites fill in." },
      { word: "Rejected", means: "A person decided the field should not be on the form. Kept in the version for the record, never shown to a site." },
      { word: "Needs a decision", means: "A filter: Draft plus Flagged, everything still waiting for a person." },
    ],
  },
  {
    title: "Filling what the protocol left out",
    terms: [
      { word: "Found in protocol", means: "Code searched the protocol text and found the unit or range stated somewhere else (eligibility criteria, a lab table). The sentence is in the note. This is the only label that clears a flag, and only when the unit was already known.",
        example: "\"Systolic values outside 60 to 250 mmHg must be re-confirmed\" gives the range 60 to 250." },
      { word: "Suggested by library", means: "The unit or range came from the client's CDASH library, not the protocol. The field stays flagged until you accept it.",
        example: "Potassium · mEq/L · 1.5 to 9 from the library." },
      { word: "Range guessed", means: "A wide plausibility range worked out from the unit or the name, to catch a misplaced decimal. Not a clinical normal range. Check it before accepting.",
        example: "Anything in mmHg: 0 to 300." },
      { word: "Accept N library suggestions / guessed ranges", means: "Approves, in one click, every flagged field whose only problem was answered by the library or a guess. It is still a human sign-off." },
      { word: "Before you lock", means: "Approved fields a site will trip over: a choice with no answer list, a number with no range or unit. They do not block the lock; they are shown so the choice is deliberate." },
    ],
  },
  {
    title: "Versions and locking",
    terms: [
      { word: "Version (v1, v2, …)", means: "Every save is a new photograph of the whole form; nothing is overwritten. v1 is what the model produced, each review save adds one more. The Versions panel shows who saved it, when, and their note.",
        example: "v1 initial extraction · v2 review: 8 changes · v5 accepted library values · v6 sign-off, locked." },
      { word: "Lock", means: "Freezes the latest version once every field is approved or rejected. After that nothing on the form can change and no re-extraction is allowed. Sites only ever see a locked form." },
      { word: "Still need a decision", means: "The count of Draft and Flagged fields keeping the Lock button disabled." },
      { word: "Extract anyway", means: "Re-runs the model on a protocol that already has a reviewed form. The old versions stay; a new v1-style draft is added. Bypasses the result cache, so it costs money." },
    ],
  },
  {
    title: "Sites, patients and data",
    terms: [
      { word: "Assigned site", means: "A hospital the sponsor has put on the study. A site sees a study only when the form is locked and the site is assigned; otherwise the study does not exist for them." },
      { word: "Subject ID", means: "The patient's study code, e.g. BGH-001. Namespaced by site so one site can never address another's patient. Patients are registered by that code, year of birth and sex, never by name, initials or full date of birth." },
      { word: "Submitted", means: "A value a site typed in. It is not data yet." },
      { word: "Approved (value)", means: "The sponsor accepted the value on Data review. It is now frozen for the site and counts in the statistics." },
      { word: "Queried (value)", means: "A query is open on this value. It cannot be approved until the query is closed." },
      { word: "History", means: "Every change to a value: old value, new value, who, when, and why (a query, if there was one)." },
      { word: "Calculated", means: "Values that follow from others: BMI from weight and height, BSA, mean arterial pressure, pulse pressure, QTcF, eGFR. Filled in automatically as the inputs are typed; a typed value that disagrees with its inputs is refused." },
    ],
  },
  {
    title: "Queries",
    terms: [
      { word: "Query", means: "A question from one side to the other about a study, a patient, a visit or one value. Whoever asks, the other side answers, and the sponsor closes it.",
        example: "Site: \"Which unit do you want for creatinine?\" Sponsor answers in words, then closes it." },
      { word: "Open / Answered / Closed", means: "Open: waiting for the other side. Answered: waiting for the sponsor to close it. Closed: settled. A value-level query returns the value to Entered when closed, so it is approved again on purpose." },
      { word: "My turn", means: "Queries where it is your move: open ones you should answer and, for the sponsor, answered ones to close. The badge in the sidebar counts them." },
      { word: "Corrected value", means: "A site answering a query about one value may attach the right number. It goes into the value's history with the query as the reason. Sponsors answer in words only." },
    ],
  },
  {
    title: "Extraction and cost",
    terms: [
      { word: "Visits", means: "The study's schedule as the model read it. You confirm or correct the list before the per-visit calls are paid for." },
      { word: "Calls", means: "Requests to the model: one to list the visits, then one per visit. A 76-page protocol is about ten." },
      { word: "From cache", means: "Calls answered from our own store of previous answers instead of the model. Identical request, identical answer, no cost. Re-running the same protocol is free." },
      { word: "Cost", means: "Measured from the tokens the provider reports for each run, at the configured prices. Shown on the Protocols and Review pages." },
      { word: "Dashboard", means: "Statistics from a fixed list of approved calculations, computed on approved values only. Each number is shown next to an independent recomputation that shares no code with the app." },
    ],
  },
];

export default function Glossary() {
  const { me } = useAuth();
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">Glossary</h1>
        <div className="muted small">What each word on these screens means{me ? `, for ${me.org.type === "site" ? "site" : "sponsor"} users and everyone else` : ""}</div>
      </div>
      {GROUPS.map((g) => (
        <div className="card glossary-group" key={g.title}>
          <h2 className="glossary-title">{g.title}</h2>
          <dl className="glossary">
            {g.terms.map((t) => (
              <div className="glossary-term" key={t.word}>
                <dt>{t.word}</dt>
                <dd>
                  {t.means}
                  {t.example && <div className="glossary-example">e.g. {t.example}</div>}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
