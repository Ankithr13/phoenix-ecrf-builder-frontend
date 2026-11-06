"""The Foundation form: the first form on every protocol.

Put there by code, not proposed by the model, because a sponsor asked for the
same opening fields on every study whatever the protocol says. So these fields
have no protocol quote to check, and the verifier skips them by their origin
and for no other reason.
"""

from ecrf import cdash
from ecrf.schema import FieldDef, Source, VisitForm

VISIT = "Foundation"
_SOURCE = {"section": "foundation", "quote": "Standard foundation field requested by sponsor"}

# Only these may be switched off. Everything else is needed by later checks.
OPTIONAL = ("Race", "Ethnicity")


def _library_field(cdash_code: str) -> dict:
    for domain in cdash.library().values():
        for entry in domain["fields"]:
            if entry.get("cdash") == cdash_code:
                return entry
    return {}


def _field(name: str, type_: str, code: str | None, **kw) -> FieldDef:
    return FieldDef(name=name, type=type_, cdash=code, origin="foundation", verdict="unchecked",
                    source=Source(**_SOURCE), **kw)


def form() -> VisitForm:
    """A fresh copy. Codelists and ranges come from the client's library."""
    height, weight, bmi = _library_field("HEIGHT"), _library_field("WEIGHT"), _library_field("BMI")
    fields = [
        _field("Informed consent obtained", "boolean", "DSDECOD"),
        _field("Consent date", "date", "RFICDTC"),
        _field("Consent version", "text", None),
        _field("Year of birth", "integer", "BRTHDTC", min=1900),
        _field("Age at consent", "integer", None, unit="years"),
        _field("Sex", "choice", "SEX", choices=_library_field("SEX").get("choices")),
        _field("Race", "choice", "RACE", choices=_library_field("RACE").get("choices")),
        _field("Ethnicity", "choice", "ETHNIC", choices=_library_field("ETHNIC").get("choices")),
        _field("Height", "decimal", "VSORRES/HEIGHT", unit="cm", min=height.get("min"), max=height.get("max")),
        _field("Weight", "decimal", "VSORRES/WEIGHT", unit="kg", min=weight.get("min"), max=weight.get("max")),
        _field("BMI", "decimal", "BMI", unit="kg/m2", min=bmi.get("min"), max=bmi.get("max")),
        _field("Eligible", "boolean", "IEYN"),
    ]
    return VisitForm(visit=VISIT, form=VISIT, fields=fields)
