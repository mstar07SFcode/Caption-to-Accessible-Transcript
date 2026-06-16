"""Tests for the Anthropic API backend using a mocked client.

No network or API key required: we inject a fake anthropic module so the
backend's prompt assembly, JSON extraction, and result mapping are exercised
end to end.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def install_fake_anthropic(captured, response_text, batch_responses=None):
    """Install a fake `anthropic` module that records the call and returns
    a canned text block. `batch_responses` maps custom_id -> json text."""
    mod = types.ModuleType("anthropic")

    class _Msg:
        def __init__(self, text):
            self.content = [types.SimpleNamespace(text=text)]

    class _Messages:
        def __init__(self, outer):
            self._outer = outer
            self.batches = _Batches(outer)

        def create(self, **kwargs):
            captured.update(kwargs)
            return _Msg(self._outer._response)

    class _Batches:
        def __init__(self, outer):
            self._outer = outer
            self._submitted = None

        def create(self, requests):
            captured["batch_requests"] = requests
            self._submitted = requests
            return types.SimpleNamespace(id="batch_test")

        def retrieve(self, _id):
            return types.SimpleNamespace(processing_status="ended")

        def results(self, _id):
            br = self._outer._batch_responses or {}
            for req in self._submitted:
                cid = req["custom_id"]
                text = br.get(cid, '{"corrections": [], "flags": []}')
                msg = _Msg(text)
                yield types.SimpleNamespace(
                    custom_id=cid,
                    result=types.SimpleNamespace(type="succeeded", message=msg))

    class Anthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self._response = response_text
            self._batch_responses = batch_responses
            self.messages = _Messages(self)

    mod.Anthropic = Anthropic
    sys.modules["anthropic"] = mod


def check(name, cond):
    print(("PASS" if cond else "FAIL") + " " + name)
    if not cond:
        check.failed += 1
check.failed = 0


def test_cleanup_backend():
    from pipeline.parse import Cue
    captured = {}
    response = (
        'Here is the result:\n```json\n'
        '{"corrections": [{"entry": 2, "find": "balance you date", '
        '"replace": "balance sheet date", "reason": "misrecognition", '
        '"confidence": "high"}], '
        '"flags": [{"entry": 3, "found": "garbled line", "issue": "unclear", '
        '"possible": "Listen to verify"}]}\n```'
    )
    install_fake_anthropic(captured, response)

    from pipeline.api_backend import APIBackend
    from pipeline.apply import apply_cleanup

    backend = APIBackend(api_key="sk-test", model="claude-sonnet-4-6")
    cues = [Cue(1, "00:00:00.000", "00:00:02.000", "Intro."),
            Cue(2, "00:00:02.000", "00:00:05.000", "The balance you date matters."),
            Cue(3, "00:00:05.000", "00:00:07.000", "garbled line")]
    judgment = backend.cleanup(cues, {})

    check("api: model passed through", captured.get("model") == "claude-sonnet-4-6")
    # system is now a list of cacheable content blocks.
    sysblock = captured["system"][0]
    check("api: system is cacheable block",
          sysblock.get("cache_control") == {"type": "ephemeral"})
    check("api: system prompt includes rules text",
          "VERBATIM" in sysblock["text"] or "Verbatim" in sysblock["text"])
    check("api: rules injected (no placeholder left)",
          "{RULES}" not in sysblock["text"])
    check("api: cue text sent", "balance you date" in captured["messages"][0]["content"])
    check("api: parsed 1 correction", len(judgment.corrections) == 1)
    check("api: parsed 1 flag", len(judgment.flags) == 1)

    cues, corr, rev = apply_cleanup(cues, judgment)
    check("api: correction applied to cue",
          cues[1].text == "The balance sheet date matters.")
    check("api: flag became review entry", len(rev) == 1 and rev[0].entry == 3)


def test_publish_backend():
    from pipeline.parse import Cue
    captured = {}
    response = ('{"sections": [{"level": 2, "title": "Overview", "start_entry": 1}], '
                '"paragraph_breaks": [1, 2], '
                '"doubled_words": [{"entry": 2, "find": "the the", "replace": "the"}], '
                '"sic": []}')
    install_fake_anthropic(captured, response)

    from pipeline.api_backend import APIBackend
    from pipeline.publish import build_html

    backend = APIBackend(api_key="sk-test")
    cues = [Cue(1, "00:00:00.000", "00:00:02.000", "Welcome."),
            Cue(2, "00:00:02.000", "00:00:05.000", "Here is the the topic.")]
    judgment = backend.publish(cues, {"title": "Transcript Demo"})
    check("publish api: title defaulted", judgment.title == "Transcript Demo")
    check("publish api: 1 section", len(judgment.sections) == 1)

    html = build_html(cues, judgment, title="Transcript Demo")
    check("publish api: doubled word removed", "the the" not in html)
    check("publish api: section heading present", "<h2>Overview</h2>" in html)


def test_json_extraction_plain():
    install_fake_anthropic({}, '{"corrections": [], "flags": []}')
    from pipeline.api_backend import _extract_json
    check("extract: plain json", _extract_json('{"a": 1}') == {"a": 1})
    check("extract: fenced json",
          _extract_json('```json\n{"a": 2}\n```') == {"a": 2})
    check("extract: prose-wrapped",
          _extract_json('Sure!\n{"a": 3}\nDone.') == {"a": 3})


def test_cleanup_batch():
    from pipeline.parse import Cue
    captured = {}
    batch_responses = {
        "r0": '{"corrections": [{"entry": 1, "find": "teh", "replace": "the", '
              '"reason": "typo", "confidence": "high"}], "flags": []}',
        "r1": '{"corrections": [], "flags": [{"entry": 1, "found": "x", '
              '"issue": "y", "possible": "Listen to verify"}]}',
    }
    install_fake_anthropic(captured, "{}", batch_responses=batch_responses)

    from pipeline.api_backend import APIBackend
    backend = APIBackend(api_key="sk-test", poll_interval=0)
    items = [
        ("FileA", [Cue(1, "00:00:00.000", "00:00:01.000", "teh start")]),
        ("FileB", [Cue(1, "00:00:00.000", "00:00:01.000", "x")]),
    ]
    out = backend.cleanup_batch(items)
    check("batch: 2 results", len(out) == 2)
    check("batch: requests carried cache_control",
          captured["batch_requests"][0]["params"]["system"][0]["cache_control"]
          == {"type": "ephemeral"})
    check("batch: custom_ids are safe", captured["batch_requests"][0]["custom_id"] == "r0")
    check("batch: FileA correction parsed", len(out["FileA"].corrections) == 1)
    check("batch: FileB flag parsed", len(out["FileB"].flags) == 1)


if __name__ == "__main__":
    for fn in [test_cleanup_backend, test_publish_backend, test_cleanup_batch,
               test_json_extraction_plain]:
        print(f"\n# {fn.__name__}")
        fn()
    print(f"\n{'ALL PASSED' if check.failed == 0 else str(check.failed) + ' FAILED'}")
    sys.exit(1 if check.failed else 0)
