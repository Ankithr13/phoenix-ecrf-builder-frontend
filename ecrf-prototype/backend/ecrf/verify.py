"""Stage 3. The grounding check.

Every field's quote must be found in the protocol text or the field is
dropped. No model is involved, which is the point: this step cannot be
talked round, and it kills the primary failure mode where the model
produces a plausible field with a plausible-looking citation.

Two tiers, because exact matching alone is too strict. Models paraphrase
while believing they are quoting, dropping a comma or writing "5" for
"five". The quote is substantively right and a string comparison says no.

THE THRESHOLD IS A PLACEHOLDER. 90 is a starting guess. It must be tuned
against the answer key: too strict rejects good fields, too loose lets a
fabrication built from real protocol vocabulary through.
"""

import re

from rapidfuzz import fuzz

from ecrf.ingest import Document
from ecrf.schema import FieldDef, Rejection, Verdict


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


# Section selection labels each chunk it sends the model as
# "[Section 7.3] Title". Models copy that label into the quote, and since
# it is our label rather than protocol text, the quote then fails to match
# by a few points and a good field is thrown away. Six of six rejections on
# one stored protocol were exactly this.
_SECTION_LABEL = re.compile(r"^\s*\[section[^\]]*\]\s*", re.IGNORECASE)


def clean_quote(quote: str) -> str:
    """Remove a leading context label that was never part of the protocol."""
    return _SECTION_LABEL.sub("", quote, count=1)


def locate(quote: str, text: str) -> tuple[Verdict, float, int]:
    """Return (verdict, score, offset). Offset is -1 when not found.

    The score is always MEASURED, never asserted. An earlier version
    short-circuited a verbatim hit to a hardcoded 100.0, which made the
    number on screen a claim by this function rather than the result of a
    comparison. A reviewer cannot tell those apart, and a hardcoded number
    cannot be wrong in a way anyone would notice.

    So the similarity is computed for every quote. A verbatim hit still
    scores 100, because that is what comparing a string to itself returns,
    and `verdict` records HOW it matched while `score` records how well.
    """
    q = _norm(quote)
    t = _norm(text)

    # rapidfuzz partial_ratio_alignment finds the best matching window.
    al = fuzz.partial_ratio_alignment(q, t)
    if al is None:
        return "rejected", 0.0, -1
    score = float(al.score)

    i = t.find(q)
    if i >= 0:
        return "exact", score, i
    return "approximate", score, al.dest_start


def check_field(field: FieldDef, doc: Document, threshold: int) -> FieldDef:
    # A foundation field was put on the form by code and quotes nothing. This
    # is the one exemption, and it is by origin, which the model cannot set.
    if field.origin == "foundation":
        field.verdict = "unchecked"
        return field
    field.source.quote = clean_quote(field.source.quote)
    verdict, score, _ = locate(field.source.quote, doc.text)
    # The score is rounded BEFORE the comparison, so the number the reviewer
    # sees is the number the decision was made on. Comparing the raw value
    # let a field scoring 89.96 be rejected and then displayed as 90.0%.
    score = round(score, 1)
    # The threshold applies to every field, however it matched. Exempting
    # verbatim hits would mean the one route that skips the check is also
    # the one nobody looks at.
    if score < threshold:
        verdict = "rejected"
    field.verdict = verdict
    field.match_score = score
    if verdict == "rejected":
        field.status = "rejected"
    elif field.issue != "none":
        field.status = "flagged"
    return field


def filter_fields(
    visit: str, fields: list[FieldDef], doc: Document, threshold: int
) -> tuple[list[FieldDef], list[Rejection]]:
    """Return (kept, rejections). Rejected fields are logged with their
    quote. That log is evidence the fabrication check fires on real input,
    and the data used to tune the threshold. Never discard silently."""
    kept: list[FieldDef] = []
    rejected: list[Rejection] = []
    for f in fields:
        f = check_field(f, doc, threshold)
        if f.verdict == "rejected":
            rejected.append(Rejection(
                visit=visit, name=f.name, quote=f.source.quote,
                section=f.source.section, score=f.match_score or 0.0,
                reason="quote not found in protocol text",
            ))
        else:
            kept.append(f)
    return kept, rejected
