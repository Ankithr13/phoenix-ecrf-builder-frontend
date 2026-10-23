"""Offline backend. Replays a recorded extraction for the bundled sample
protocol so the whole pipeline runs with no API key and no GPU.

If the uploaded protocol is not the sample, it returns an empty result with
a clear note rather than pretending. Set ECRF_BACKEND=openai_compat for
anything real.

The per_form strategy is derived from the same recording: fields with the
same CDASH domain and the same set of visits become one form, so the two
strategies cover the same visit x field grid and can be compared.
"""

import json

from ecrf import cdash
from ecrf.config import config
from ecrf.extract.base import Usage
from ecrf.schema import ExtractionPlan, FieldDef, FormFields, FormPlan, VisitForm, VisitList

SAMPLE_MARKER = "PHX-401-201"


class MockExtractor:
    name = "mock"
    model = "recorded/PHX-401-201"

    def __init__(self) -> None:
        with open(config.data_dir / "recorded" / "PHX-401-201.json") as f:
            self.fixture = json.load(f)
        self.usage = Usage()

    def begin_run(self, protocol_hash: str, force: bool = False) -> None:
        self.usage = Usage()

    def _is_sample(self, text: str) -> bool:
        return SAMPLE_MARKER in text[:2000]

    # ------------------------------------------------------- per_visit
    def list_visits(self, protocol_text: str) -> VisitList:
        if not self._is_sample(protocol_text):
            return VisitList(visits=[])
        return VisitList(visits=self.fixture["visits"])

    def fields_for_visit(self, protocol_text: str, visit: str, visits: list[str]) -> VisitForm:
        if not self._is_sample(protocol_text):
            return VisitForm(visit=visit, fields=[])
        form = self.fixture["forms"].get(visit)
        if not form:
            return VisitForm(visit=visit, fields=[])
        return VisitForm.model_validate(form)

    # -------------------------------------------------------- per_form
    def _forms(self) -> dict[str, tuple[list[str], list[FieldDef]]]:
        """form name -> (visits, fields), grouped by domain and visit set."""
        visits = self.fixture["visits"]
        seen: dict[str, tuple[list[str], FieldDef]] = {}
        for v in visits:
            for raw in self.fixture["forms"].get(v, {}).get("fields", []):
                fd = FieldDef.model_validate(raw)
                if fd.name not in seen:
                    seen[fd.name] = ([], fd)
                seen[fd.name][0].append(v)
        groups: dict[tuple[str, tuple[str, ...]], list[FieldDef]] = {}
        for _name, (vs, fd) in seen.items():
            hit = cdash.match(fd.name)
            label = cdash.library()[hit[0]]["label"].split(" (")[0] if hit else "Other"
            groups.setdefault((label, tuple(vs)), []).append(fd)
        out: dict[str, tuple[list[str], list[FieldDef]]] = {}
        for (label, vs), fields in groups.items():
            name, n = label, 2
            while name in out:
                name, n = f"{label} ({n})", n + 1
            out[name] = (list(vs), fields)
        return out

    def plan(self, protocol_text: str) -> ExtractionPlan:
        if not self._is_sample(protocol_text):
            return ExtractionPlan(visits=[], forms=[])
        forms = [FormPlan(name=n, visits=vs) for n, (vs, _) in self._forms().items()]
        return ExtractionPlan(visits=self.fixture["visits"], forms=forms)

    def fields_for_form(self, protocol_text: str, form: str, form_visits: list[str],
                        visits: list[str]) -> FormFields:
        if not self._is_sample(protocol_text):
            return FormFields(form=form, fields=[])
        entry = self._forms().get(form)
        return FormFields(form=form, fields=[f.model_copy(deep=True) for f in entry[1]] if entry else [])
