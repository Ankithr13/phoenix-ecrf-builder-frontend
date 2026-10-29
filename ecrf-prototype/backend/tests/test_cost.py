"""Stage 4: fewer calls, lower cost. The OpenAI client is replaced by a fake
that answers from the recorded fixture and counts what it was asked."""

import json
import os
import re
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from conftest import BUILDER, login
from openai import BadRequestError

import ecrf.extract.base as base_mod
import ecrf.extract.openai_compat as oc_mod
from ecrf import pipeline
from ecrf.config import config
from ecrf.ingest import load

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample", "PHX-401-201_protocol.pdf")
FIXTURE = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "recorded", "PHX-401-201.json")))
USAGE = {"prompt_tokens": 1000, "completion_tokens": 50, "cached_tokens": 800, "reasoning_tokens": 5}


def _answer(messages: list[dict]) -> str:
    last = messages[-1]["content"]
    if "List the study visits" in last:
        return json.dumps({"visits": FIXTURE["visits"]})
    m = re.search(r'"([^"]+)" visit only', last)
    if m:
        return json.dumps(FIXTURE["forms"][m.group(1)])
    return "{}"


class FakeCompletions:
    def __init__(self, calls: list, finish: str = "stop", reject: str | None = None):
        self.calls, self.finish, self.reject = calls, finish, reject

    def create(self, **kw):
        if self.reject and self.reject in kw:
            raise BadRequestError(
                f"Unrecognized request argument supplied: {self.reject}",
                response=httpx.Response(400, request=httpx.Request("POST", "http://fake")), body=None)
        self.calls.append(kw)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=_answer(kw["messages"])),
                                     finish_reason=self.finish)],
            usage=SimpleNamespace(
                prompt_tokens=USAGE["prompt_tokens"], completion_tokens=USAGE["completion_tokens"],
                prompt_tokens_details=SimpleNamespace(cached_tokens=USAGE["cached_tokens"]),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=USAGE["reasoning_tokens"])),
        )


@pytest.fixture
def fake_llm(monkeypatch):
    """Patch the SDK client and give the adapter a key and an OpenAI host."""
    calls: list = []
    state = {"finish": "stop", "reject": None}

    class FakeOpenAI:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=FakeCompletions(calls, state["finish"], state["reject"]))

    monkeypatch.setattr(oc_mod, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(base_mod, "config", replace(
        config, llm_api_key="test-key", llm_base_url="https://api.openai.com/v1", llm_model="gpt-test"))
    calls_obj = SimpleNamespace(calls=calls, state=state)
    return calls_obj


def _run(c, pid, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = c.post(f"/api/protocols/{pid}/extract?backend=openai_compat&{q}")
    return r


def test_second_identical_run_makes_no_api_calls(client, demo_accounts, fake_llm):
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    s1 = _run(client, pid).json()["summary"]
    assert s1["llm_calls_made"] == 6 and s1["llm_calls_from_cache"] == 0   # 1 + 5 visits
    assert s1["est_cost_usd"] > 0
    assert len(fake_llm.calls) == 6

    s2 = _run(client, pid).json()["summary"]
    assert s2["llm_calls_made"] == 0 and s2["llm_calls_from_cache"] == 6
    assert s2["est_cost_usd"] == 0 and len(fake_llm.calls) == 6, "nothing left the process"
    assert s2["fields_kept"] == s1["fields_kept"]


def test_force_bypasses_cache_reads(client, demo_accounts, fake_llm):
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    _run(client, pid)
    s = _run(client, pid, force="true").json()["summary"]
    assert s["llm_calls_made"] == 6 and s["llm_calls_from_cache"] == 0
    assert len(fake_llm.calls) == 12


def test_truncated_output_is_refused(client, demo_accounts, fake_llm):
    fake_llm.state["finish"] = "length"
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    r = _run(client, pid)
    assert r.status_code == 502 and "cut off" in r.json()["detail"]
    assert client.get(f"/api/protocols/{pid}/draft").json()["draft"] is None, "no version written"


def test_usage_is_summed_and_priced(client, demo_accounts, fake_llm):
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    s = _run(client, pid).json()["summary"]
    n = 6
    assert s["input_tokens"] == n * 1000 and s["cached_input_tokens"] == n * 800
    assert s["output_tokens"] == n * 50 and s["reasoning_tokens"] == n * 5
    expected = (n * 200 * config.price_input_per_m + n * 800 * config.price_cached_input_per_m
                + n * 50 * config.price_output_per_m) / 1e6
    assert s["est_cost_usd"] == round(expected, 4)


def test_openai_gets_cache_hints_and_an_output_cap(client, demo_accounts, fake_llm):
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    _run(client, pid)
    kw = fake_llm.calls[0]
    assert kw["max_completion_tokens"] == config.max_output_tokens
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["reasoning_effort"] == "none"
    assert kw["extra_body"]["prompt_cache_key"].startswith("ecrf-")
    assert kw["extra_body"]["prompt_cache_retention"] == "24h"
    keys = {c["extra_body"]["prompt_cache_key"] for c in fake_llm.calls}
    assert len(keys) == 1, "every call of a run routes to the same provider cache"
    # The stable prefix: system + protocol text identical on every call.
    prefixes = {c["messages"][1]["content"].split("\n\nTASK:")[0].split("\n\nSTUDY VISITS:")[0] for c in fake_llm.calls}
    assert len(prefixes) == 1


def test_rejected_parameter_is_dropped_and_the_run_continues(client, demo_accounts, fake_llm):
    fake_llm.state["reject"] = "reasoning_effort"
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    r = _run(client, pid)
    assert r.status_code == 200
    assert all("reasoning_effort" not in c for c in fake_llm.calls)
    assert len(fake_llm.calls) == 6


def test_per_form_covers_the_same_grid_as_per_visit():
    doc = load(SAMPLE)
    a = pipeline.run(SAMPLE, 1, backend="mock", doc=doc, strategy="per_visit")
    b = pipeline.run(SAMPLE, 1, backend="mock", doc=doc, strategy="per_form")
    grid = lambda d: {(f.visit, x.name) for f in d.forms for x in f.fields}  # noqa: E731
    assert grid(a) == grid(b)
    assert [f.visit for f in a.forms] == [f.visit for f in b.forms]
    assert b.summary["strategy"] == "per_form" and b.summary["forms"] > 0
    assert b.summary["forms"] < b.summary["visits"] * 3, "fewer forms than visit x domain pairs"


def test_two_step_extraction_lets_a_person_fix_the_visits(client, demo_accounts):
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    assert client.post(f"/api/protocols/{pid}/extract/fields").status_code == 409, "visits first"

    plan = client.post(f"/api/protocols/{pid}/extract/visits").json()
    assert plan["visits"] == FIXTURE["visits"] and plan["confirmed"] is False
    assert plan["estimated_calls"] == 5

    edited = [v for v in plan["visits"] if v != "Early Termination"]
    edited[1] = "Day 1 (Baseline)"
    r = client.put(f"/api/protocols/{pid}/visits", json={"visits": edited})
    assert r.status_code == 200 and r.json()["confirmed"] is True and r.json()["estimated_calls"] == 4
    assert client.put(f"/api/protocols/{pid}/visits", json={"visits": ["A", "A"]}).status_code == 422

    r = client.post(f"/api/protocols/{pid}/extract/fields")
    assert r.status_code == 200
    draft = client.get(f"/api/protocols/{pid}/draft").json()["draft"]
    assert [f["visit"] for f in draft["forms"]] == edited
    assert draft["summary"]["visits"] == 4 and draft["summary"]["llm_calls_made"] == 0  # mock


def test_one_malformed_field_does_not_lose_the_visit(client, demo_accounts, fake_llm, monkeypatch):
    """Seen live: a quote of 14 characters copied from a table cell failed
    the schema, the retry repeated it, and the whole run died with a 502.
    The bad field is dropped and logged; the rest of the visit survives."""
    import sys
    good = _answer

    def with_a_bad_field(messages):
        out = good(messages)
        if '"fields"' in out:
            obj = json.loads(out)
            obj["fields"].append({"name": "Demographics", "type": "text",
                                  "source": {"section": "1", "quote": "Demographics X"}})
            return json.dumps(obj)
        return out

    monkeypatch.setattr(sys.modules[__name__], "_answer", with_a_bad_field)
    login(client, BUILDER)
    pid = client.post("/api/protocols/sample").json()["id"]
    r = _run(client, pid)
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["llm_calls_made"] == 11, "each of the 5 visits was retried once, then salvaged"
    draft = client.get(f"/api/protocols/{pid}/draft").json()["draft"]
    bad = [x for x in draft["rejections"] if x["name"] == "Demographics"]
    assert len(bad) == 5 and all("invalid field" in x["reason"] and "20" in x["reason"] for x in bad)
    assert all(x["quote"] == "Demographics X" for x in bad)
    assert s["fields_kept"] > 0 and s["rejected"] == len(draft["rejections"])
