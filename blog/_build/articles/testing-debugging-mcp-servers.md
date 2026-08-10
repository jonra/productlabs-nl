---
title: Testing and debugging MCP servers before you ship
slug: testing-debugging-mcp-servers
dek: Three layers need testing and most teams only cover one. A working pytest suite you can copy, including the protocol conformance checks the current revision made necessary.
type: article
topic: mcp
date: 2026-08-10
updated: 2026-08-10
reading_time: 9
badge_new: true
order: 1
meta_title: "Testing and Debugging MCP Servers Before You Ship"
meta_description: A practical test strategy for MCP servers — protocol conformance, schema quality, and tool-selection accuracy — with a pytest suite you can copy.
keywords: [test mcp server, debug mcp server, mcp server errors, mcp conformance testing, pytest mcp]
related: [mcp-2026-07-28-migration-stateless-protocol, mcp-tool-schema-design, mcp-tool-definition-token-cost]
sources:
  - MCP specification 2026-07-28 — Versioning and Compatibility|https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
  - MCP specification 2026-07-28 — Transports|https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
---

Most MCP servers we review have tests for their business logic and nothing else. The
business logic is rarely what breaks.

There are three layers, and they fail in different ways:

1. **Protocol conformance** — does the server behave the way the specification says,
   including in the error cases
2. **Schema quality** — are the tool definitions well-formed, bounded, and stable
3. **Model-facing behaviour** — given a realistic request, does the model pick the right
   tool with the right arguments

Layer one is mechanical and cheap. Layer two is mechanical and almost never done. Layer
three needs a model in the loop and is where the interesting failures live.

## Layer 1: protocol conformance

The current revision made this more important than it used to be. With no `initialize`
handshake, version handling is per-request, and `UnsupportedProtocolVersionError` is a
first-class part of your server's contract rather than an edge case.

Three things must be true and are easy to assert:

- `server/discover` is implemented — it is mandatory
- An unsupported version returns code `-32022` with a populated `supported` list and the
  `requested` value echoed back
- A request with no version is rejected rather than silently defaulting

That last one matters. A server that quietly assumes the latest version when `_meta` is
absent will appear to work with a broken client and fail confusingly later.

## Layer 2: schema quality

These are assertions about your tool definitions, and they catch a surprising amount.

The most valuable one is not obvious: **assert that the tool block serialises
byte-identically across calls.** If it does not, prompt caching will never hit, and the
symptom — a bill roughly 25% higher than expected with no functional difference — is
extremely hard to trace back to its cause. A three-line test catches it forever.

## The suite

This runs. The stub `server.py` stands in for whatever your real request handling looks
like; replace it with an import of your own handler and the tests carry over.

```python
import json
import pytest
from server import handle, RpcError, MODERN, SUPPORTED

def req(method, params=None, version=MODERN):
    return {"method": method,
            "params": params or {},
            "_meta": {"io.modelcontextprotocol/protocol-version": version}}

# ── Layer 1: protocol conformance ────────────────────────────────────────────
def test_discover_is_implemented():
    assert MODERN in handle(req("server/discover"))["protocolVersions"]

def test_unsupported_version_returns_32022_with_supported_list():
    with pytest.raises(RpcError) as e:
        handle(req("tools/list", version="1900-01-01"))
    assert e.value.code == -32022
    assert e.value.data["supported"] == SUPPORTED
    assert e.value.data["requested"] == "1900-01-01"

def test_missing_version_is_rejected():
    with pytest.raises(RpcError) as e:
        handle({"method": "tools/list", "_meta": {}})
    assert e.value.code == -32022

# ── Layer 2: schema quality ──────────────────────────────────────────────────
@pytest.fixture
def tools():
    return handle(req("tools/list"))["tools"]

def test_every_tool_has_name_and_description(tools):
    for t in tools:
        assert t.get("name") and t.get("description")

def test_every_parameter_is_described(tools):
    for t in tools:
        for prop, spec in t["inputSchema"].get("properties", {}).items():
            assert spec.get("type"), f"{t['name']}.{prop} has no type"

def test_numeric_parameters_are_bounded(tools):
    for t in tools:
        for prop, spec in t["inputSchema"].get("properties", {}).items():
            if spec.get("type") == "integer":
                assert "minimum" in spec and "maximum" in spec, \
                    f"{t['name']}.{prop} is unbounded"

def test_tool_definitions_serialise_deterministically(tools):
    a = json.dumps(handle(req("tools/list")), sort_keys=False)
    b = json.dumps(handle(req("tools/list")), sort_keys=False)
    assert a == b, "tool block is not byte-stable; caching will never hit"

# ── Layer 3: error messages are actionable ───────────────────────────────────
def test_missing_required_argument_names_the_field():
    with pytest.raises(RpcError) as e:
        handle(req("tools/call", {"arguments": {}}))
    assert "query" in e.value.message and "Retry" in e.value.message

def test_out_of_range_error_shows_received_value():
    with pytest.raises(RpcError) as e:
        handle(req("tools/call", {"arguments": {"query": "x", "limit": 500}}))
    assert "500" in e.value.message and "1 and 25" in e.value.message

def test_empty_result_is_explicit_not_ambiguous():
    out = handle(req("tools/call", {"arguments": {"query": "nothing"}}))
    assert out["total"] == 0 and out["message"]
```

```
$ python3 -m pytest -q
..........                                                    [100%]
10 passed in 0.01s
```

Those last three tests are unusual and worth keeping. They assert that error messages are
*useful to a model* — that they name the field, show the received value, and say what to
do. Error text is normally untested because it is "just a string". Here it is part of the
control flow: the model reads it and decides what to do next. Test it like an interface,
because it is one.

## Layer 3: behavioural testing

Everything above runs without a model. This layer needs one, and it is where the failures
that actually reach users live.

You are measuring two things:

- **Selection accuracy** — given a realistic user request, is the right tool called?
- **Argument accuracy** — are the arguments well-formed and semantically correct?

Build a set of realistic requests phrased the way users phrase them, not the way your
documentation phrases them. Pull them from real logs if you have them. Include the
ambiguous ones and the ones that should route to a *different* tool, because false
positives matter as much as false negatives.

Then run each case several times. Tool selection is non-deterministic. A definition that
works four times in five looks perfect in a manual test and produces a steady trickle of
production failures. Three runs minimum, and look at the spread rather than the mean.

When a case fails, fix the tool definition rather than the system prompt. A system prompt
workaround does not travel with your server to other clients, and it has to be maintained
forever. Usually the fix is a "do not use for" clause pointing at the tool that should
have been called.

## Failure modes worth testing for explicitly

From servers we have debugged, these recur often enough to be worth a permanent test:

**Unbounded returns.** A query that matches everything returns everything, blows the
context window, and fails in a way that looks like a model problem. Cap server-side and
test the cap.

**Silent nulls.** A tool returning `null` for a missing record is ambiguous — the model
cannot distinguish "not found" from "found, empty". Return an explicit message.

**Shape drift.** A tool that returns an object for one result and an array for several.
Pick one shape and assert it.

**Timeouts with no signal.** A tool that hangs gives the model nothing to work with. Set a
timeout and return an actionable error when you hit it.

**Non-deterministic key ordering.** Covered above, and the highest-value test in the suite
for anyone who has caching configured.

**Schema drift between code and definition.** The handler accepts a parameter the schema
does not declare, or vice versa. Assert that declared parameters and handled parameters
match.

## Debugging when it is already broken

A working order for the common symptoms:

**"The model never calls my tool."** Check it is in `tools/list` at all. Then read the
description as if you had never seen the tool — does it say when to use it, in the words a
user would use? Then check for a neighbouring tool that is winning the selection.

**"The model calls it with bad arguments."** Almost always missing format detail in the
parameter description. Dates and identifiers are the usual suspects. Add an example inline.

**"It works in my client but not theirs."** Era mismatch. Check whether the other client is
legacy and whether your server supports both. The compatibility matrix in the versioning
spec tells you exactly which combinations fail.

**"It worked yesterday."** Diff your serialised tool definitions. Something regenerated
differently.

**"Costs went up but nothing changed."** Check `cache_read_input_tokens` against
`cache_creation_input_tokens`. If creation is consistently large, your cache stopped
hitting — usually because a tool definition changed, which invalidates everything.

## On logging

You cannot debug an agent loop from a stack trace. Log, per tool call: the tool name, the
full arguments, the result summary, the duration, and a correlation ID tying the whole run
together.

Log tool *errors* with the same care, including the message you sent back to the model.
When you are working out why a run went sideways, the error text the model actually read
is frequently the answer, and it is the thing least likely to have been recorded.

## A pre-ship checklist

- `server/discover` implemented and tested
- `UnsupportedProtocolVersionError` returns `-32022` with a populated `supported` list
- Missing protocol version is rejected, not defaulted
- Every tool has a description containing use-when and do-not-use-for
- Every parameter has a type, a description, and bounds where numeric
- Tool block verified byte-stable across calls
- Error messages name the field, show the value, and state the fix
- Results are capped server-side and report a total
- Selection accuracy measured over repeated runs on realistic phrasing
- Tool calls and tool errors logged with a correlation ID
- If dual-era: both failing rows of the compatibility matrix tested
