---
title: What your MCP tool definitions cost on every single request
slug: mcp-tool-definition-token-cost
dek: Tool definitions sit in the context window before the user has typed anything, on every request, forever. Here is a script that measures the bill — and the reason a one-character change to a description can invalidate your entire cache.
type: article
topic: mcp
date: 2026-07-20
updated: 2026-08-10
reading_time: 8
order: 2
meta_title: "What Your MCP Tool Definitions Cost You Per Request"
meta_description: Measure the token cost of MCP tool definitions with a working script, understand how caching applies, and cut the fixed per-request overhead of a multi-server deployment.
keywords: [mcp token cost, claude tool definition tokens, reduce mcp context, tool definition caching, mcp context window]
related: [mcp-tool-schema-design, claude-prompt-caching-guide, claude-model-selection-cost-per-task]
sources:
  - Claude Platform Docs — Prompt caching|https://platform.claude.com/docs/en/build-with-claude/prompt-caching
---

Tool definitions are not free and they are not occasional. They are part of the prompt, on
every request, before the user has said a word.

On a single small server nobody notices. On a realistic deployment — a user with six or
seven MCP servers connected, each exposing eight to fifteen tools — the fixed overhead per
request becomes one of the larger line items in the bill, and one almost nobody has
measured.

## Measure it first

Here is a script that reports the per-tool token cost of any MCP server's tool set.

It runs in two modes. With an API key it measures each tool's **marginal** cost through the
token counting endpoint, which is exact. Without one it falls back to a character-based
approximation that is good enough for finding your worst offenders.

```python
#!/usr/bin/env python3
"""Report the per-request token cost of a set of MCP tool definitions."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path


def load_tools(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tools = data.get("tools", data) if isinstance(data, dict) else data
    if not isinstance(tools, list):
        sys.exit("Expected a list of tools, or an object with a 'tools' key.")
    return tools


def normalise(tool: dict) -> dict:
    """Map an MCP tool definition onto the Claude API tool shape."""
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    return {
        "name": tool.get("name", "<unnamed>"),
        "description": tool.get("description", ""),
        "input_schema": schema,
    }


def estimate_tokens(tool: dict) -> int:
    """Key-free approximation. Serialised JSON averages ~3.7 chars/token."""
    return round(len(json.dumps(tool, separators=(",", ":"))) / 3.7)


def count_exact(tools: list[dict], model: str) -> list[int]:
    """Marginal cost of each tool, measured by difference."""
    import anthropic
    client = anthropic.Anthropic()
    msg = [{"role": "user", "content": "x"}]

    def count(subset):
        r = client.messages.count_tokens(model=model, messages=msg, tools=subset)
        return r.input_tokens

    base = count([])
    running, out = base, []
    for i in range(len(tools)):
        total = count(tools[: i + 1])
        out.append(total - running)
        running = total
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--price", type=float, default=5.0,
                    help="base input price per million tokens")
    ap.add_argument("--requests", type=int, default=100_000,
                    help="requests per month, for the projection")
    ap.add_argument("--estimate", action="store_true", help="force key-free mode")
    args = ap.parse_args()

    tools = [normalise(t) for t in load_tools(args.file)]
    if not tools:
        sys.exit("No tools found.")

    mode = "estimate"
    counts = [estimate_tokens(t) for t in tools]
    if not args.estimate:
        try:
            counts = count_exact(tools, args.model)
            mode = "exact"
        except Exception as e:
            print(f"note: falling back to estimate mode ({type(e).__name__})\n",
                  file=sys.stderr)

    order = sorted(range(len(tools)), key=lambda i: counts[i], reverse=True)
    total = sum(counts)

    width = max(len(t["name"]) for t in tools) + 2
    print(f"{'TOOL':<{width}}{'TOKENS':>8}{'SHARE':>8}")
    print("-" * (width + 16))
    for i in order:
        share = counts[i] / total * 100 if total else 0
        print(f"{tools[i]['name']:<{width}}{counts[i]:>8}{share:>7.1f}%")
    print("-" * (width + 16))
    print(f"{'TOTAL':<{width}}{total:>8}")

    uncached = total / 1_000_000 * args.price * args.requests
    cached = uncached * 0.1
    print(f"\nmode: {mode}   model: {args.model}   base input: ${args.price}/MTok")
    print(f"per request: {total} tokens before the user says anything")
    print(f"at {args.requests:,} requests/month:")
    print(f"  uncached: ${uncached:,.2f}")
    print(f"  cached:   ${cached:,.2f}  (saving ${uncached - cached:,.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Save your server's `tools/list` output to a JSON file and run it. Output looks like this —
this is a real run against a small four-tool document server:

```
TOOL                TOKENS   SHARE
----------------------------------
search_documents       202   40.6%
list_documents         110   22.1%
get_document            94   18.9%
create_ticket           92   18.5%
----------------------------------
TOTAL                  498

mode: estimate   model: claude-opus-5   base input: $5.0/MTok
per request: 498 tokens before the user says anything
at 100,000 requests/month:
  uncached: $249.00
  cached:   $24.90  (saving $224.10)
```

Four tools. Around 500 tokens. That is fine.

Now scale it the way real deployments scale. Seven servers averaging ten tools each,
with descriptions written to the standard we recommend — explicit "use when" and "do not
use for" clauses — lands in the region of 6,000–9,000 tokens of fixed overhead per request.
At Opus 5 pricing and 100,000 requests a month, that is roughly $3,000–$4,500 annually in
tool definitions alone, before anyone asks a question.

Cached, the same overhead costs about a tenth of that. Which brings us to the important
part.

## Caching tool definitions

Tool definitions sit **first** in the cache hierarchy: `tools → system → messages`. That
position is ideal — a cached prefix covering your tools also covers everything before it,
and there is nothing before it.

So the fixed overhead is exactly the kind of content prompt caching was built for. Cache
reads cost 0.1× base input. Your 6,000-token tool block drops from a real cost to a
rounding error.

There is one catch, and it is sharp.

**Any change to a tool definition invalidates the entire cache.** Not just the tools
segment — tools, system and messages, all of it. Changing a tool name, a description, or a
single parameter is a full invalidation.

For static tool sets this never comes up. For anything dynamic it is the difference between
a 90% saving and none at all. Two patterns cause silent, permanent cache misses:

**Non-deterministic serialisation.** If your tool definitions are generated from a map or
dictionary whose iteration order is not stable, the JSON differs between requests even
though the content is identical. Some languages — Go and Swift among them — randomise map
key order during JSON conversion. Everything looks correct. Nothing ever caches. Enforce
stable key ordering.

**Per-request interpolation.** Injecting a timestamp, a user ID or a session token into a
tool description regenerates it every request. If you need per-user context in a tool, put
it in the tool's *arguments*, not in its description.

The test for both: log the serialised tool block on two consecutive requests and diff them.
If they differ by a single byte, you are paying the write premium every time and never
reading.

## Cutting the definitions down

Caching handles most of the cost. But context window pressure is a separate problem —
tokens spent on tools are tokens unavailable for actual work — and in long agent loops that
matters independently of price.

**Remove tools nobody calls.** Instrument which tools are actually invoked over a month.
Most deployments have several that never fire. Every one of them costs tokens on every
request and makes the remaining tools marginally harder to select correctly.

**Consolidate variations into parameters.** `search_by_name`, `search_by_email` and
`search_by_phone` are three definitions where one `search_contacts` with a `field` enum
would do. Roughly a two-thirds saving on that group.

**Trim schema verbosity, not schema clarity.** JSON Schema has plenty of room for
redundancy — nested wrappers around single values, repeated boilerplate in every property
description, examples that duplicate an enum already listing valid values. Cut those.

**Do not cut the routing clauses.** The "do not use for" lines are the most token-expensive
part of a good description and the most valuable. A wrong tool call costs a full round trip
plus a recovery attempt, which is far more than the tokens that would have prevented it.

That last point is the trade-off to hold onto. Where you are cutting *redundancy*, cut
freely. Where you are cutting *decision criteria*, you are trading a fixed known cost for a
variable unknown one, usually badly.

**Consider deferred tool loading.** For very large tool sets, some clients support loading
only a subset up front and fetching the rest on demand. Where it is available it changes
the economics of a large deployment substantially — you pay for the tools a task actually
needs rather than every tool that exists.

## A working order

1. Export `tools/list` from each connected server.
2. Run the script. Sort by cost.
3. Delete tools nobody invokes. Check your logs, not your intuition.
4. Consolidate near-duplicates into parameterised tools.
5. Trim redundancy from schemas; leave routing clauses alone.
6. Verify your tool block serialises byte-identically across requests.
7. Confirm caching is actually hitting — `cache_read_input_tokens` should be large and
   `cache_creation_input_tokens` near zero in steady state.
8. Re-measure. Multiply by your monthly request volume so the number is in euros.

Step 6 is the one that pays for the exercise. We have seen deployments where every other
optimisation was in place and a randomised key order meant the cache had never once been
read.
