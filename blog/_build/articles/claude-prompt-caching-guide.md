---
title: Claude prompt caching — automatic, explicit, and the lookback trap
slug: claude-prompt-caching-guide
dek: The cache does not find stable content behind your breakpoint. It finds entries earlier requests already wrote. Understanding that one sentence is the difference between an 80% discount and paying a premium on every request.
type: article
topic: claude-api
date: 2026-07-16
updated: 2026-08-10
reading_time: 11
order: 7
meta_title: "Claude Prompt Caching: Automatic, Explicit, and the Lookback Trap"
meta_description: How Claude's prompt cache really works — where breakpoints belong, the 20-block lookback window, per-model minimums, and the mistake that bills you for writes you never read.
keywords: [claude prompt caching, cache_control claude, anthropic cache breakpoint, prompt cache not hitting, claude cache pricing, prompt cache prewarming]
related: [mcp-tool-definition-token-cost, claude-model-selection-cost-per-task]
sources:
  - Claude Platform Docs — Prompt caching|https://platform.claude.com/docs/en/build-with-claude/prompt-caching
---

<div class="callout">
<span class="callout-label">Pricing and model minimums verified 10 August 2026</span>
<p>Model pricing changes. One change is already scheduled — see the pricing section.
Re-check current rates before building a cost model on these numbers.</p>
</div>

Prompt caching is the highest-leverage cost optimisation available on the Claude API.
Cache reads cost a tenth of base input tokens. For a workload with a large stable prefix —
a long system prompt, a document, a set of tool definitions — that is most of your bill.

It is also the feature we most often find misconfigured, and the failure is silent. You
get charged the 25% write premium on every single request and never once read from the
cache. Your costs go *up*.

There is one sentence that prevents this, and it is worth reading twice:

> The lookback does not find stable content behind your breakpoint. It finds entries that
> earlier requests already wrote — and writes happen only at breakpoints.

Everything below follows from that.

## The mechanism, precisely

Three principles define the whole system.

**Cache writes happen only at your breakpoint.** Marking a block with `cache_control`
writes exactly one cache entry: a hash of the prefix ending at that block. The system does
not write entries for any earlier position. Because the hash is cumulative — covering
everything up to and including the breakpoint — changing any block at or before the
breakpoint produces a different hash next time.

**Cache reads look backward for entries prior requests wrote.** On each request the system
computes the prefix hash at your breakpoint and checks for a match. If there is none, it
walks backward one block at a time, checking whether the prefix hash at each earlier
position matches something already cached. It is looking for prior *writes*, not for
stable *content*.

**The lookback window is 20 blocks.** At most 20 positions are checked per breakpoint,
counting the breakpoint itself as the first. If nothing matches in that window, checking
stops — or resumes at the next explicit breakpoint, if you have one.

## The mistake that costs money

Here is the shape of it. Your prompt has a large static system context in blocks 1–5,
followed by a per-request block containing a timestamp and the user message in block 6.
You set `cache_control` on block 6, because it is the last block and that seems right.

- **Request 1:** cache write at block 6. The hash includes the timestamp.
- **Request 2:** the timestamp differs, so the prefix hash at block 6 differs. The lookback
  walks back through blocks 5, 4, 3, 2, 1 — and the system never wrote an entry at any of
  those positions. No cache hit.

You pay a fresh cache write on every request and never get a read. You have made the
workload more expensive than not caching at all.

The fix is one line: move `cache_control` to block 5, the last block that stays identical
across requests. Every subsequent request then reads the cached prefix.

**Automatic caching falls into the same trap.** It places the breakpoint on the last
cacheable block — which in this structure is exactly the block that changes every request.
For a prompt with a varying suffix, use an explicit breakpoint on the static prefix
instead.

## Automatic versus explicit

**Automatic caching** takes a single `cache_control` field at the top level of the request
body. The system applies the breakpoint to the last cacheable block and moves it forward
as the conversation grows.

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    system="You are an AI assistant tasked with analyzing literary works...",
    messages=[{"role": "user", "content": "Analyze the major themes in 'Pride and Prejudice'."}],
)
```

This is the right default for **multi-turn conversations**, where each turn appends to a
history that never changes retroactively. The breakpoint advancing with the conversation
is exactly what you want, and you never touch a marker.

**Explicit breakpoints** put `cache_control` on individual content blocks. Use them when
sections change at different frequencies, or when your last block varies per request.

The two compose. A common and effective pattern is an explicit breakpoint on the system
prompt plus automatic caching for the conversation:

```json
{
  "model": "claude-opus-5",
  "max_tokens": 1024,
  "cache_control": { "type": "ephemeral" },
  "system": [
    {
      "type": "text",
      "text": "You are a helpful assistant.",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [{ "role": "user", "content": "What are the key terms?" }]
}
```

Note that the automatic breakpoint consumes one of the four available slots. If you
already have four explicit breakpoints, adding a top-level `cache_control` returns a `400`.

## Growing conversations and the 20-block cliff

This one is subtle because it works fine, then stops.

Suppose you append blocks each turn and set the breakpoint on the final block:

- **Turn 1:** 10 blocks, breakpoint at block 10. Nothing cached yet. Entry written at 10.
- **Turn 2:** 15 blocks, breakpoint at block 15. No entry there, so the lookback walks back
  to block 10 and finds the turn-1 entry. Hit. Blocks 11–15 processed fresh, new entry
  written at 15.
- **Turn 3:** 35 blocks, breakpoint at block 35. The lookback checks 20 positions — blocks
  35 down to 16 — and finds nothing. The turn-2 entry at block 15 is one position outside
  the window. **No hit.**

Nothing errors. Your bill just quietly doubles.

The rule: in a growing conversation, the final block works as a breakpoint **as long as
each turn adds fewer than 20 blocks**. If a turn can add more — a burst of tool calls, a
batch of retrieved documents — add a second breakpoint closer to that position *from the
start*, so a write accumulates there before you need it.

Breakpoints themselves are free. You are charged for writes and reads, not for markers.
There is no cost argument against placing them defensively.

## Minimum cacheable length

Below the minimum, caching is silently skipped. No error, no warning.

| Model | Minimum cacheable prompt |
|---|---|
| Claude Opus 5, Fable 5, Mythos 5 | 512 tokens |
| Claude Opus 4.8, Sonnet 5, Sonnet 4.6, Sonnet 4.5 | 1,024 tokens |
| Claude Mythos Preview, Opus 4.7 | 2,048 tokens |
| Claude Opus 4.6, Opus 4.5, Haiku 4.5 | 4,096 tokens |

Haiku 4.5 having a 4,096-token floor surprises people, because Haiku is the model most
often used for short, high-volume calls — precisely the shape that cannot be cached.

To check whether a prompt cached at all: if both `cache_creation_input_tokens` and
`cache_read_input_tokens` are `0`, it did not. If you are just under the threshold,
expanding the cached content to reach it is often worth doing — reads are cheap enough
that crossing the line pays for the extra tokens.

## Pricing, and a change you need to diary

Multipliers against base input price:

- 5-minute cache write: **1.25×**
- 1-hour cache write: **2×**
- Cache read: **0.1×**

Current rates per million tokens:

| Model | Base input | 5m write | 1h write | Cache read | Output |
|---|---|---|---|---|---|
| Claude Opus 5 | $5 | $6.25 | $10 | $0.50 | $25 |
| Claude Sonnet 5 (to 31 Aug 2026) | $2 | $2.50 | $4 | $0.20 | $10 |
| Claude Sonnet 5 (from 1 Sep 2026) | $3 | $3.75 | $6 | $0.30 | $15 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 | $5 |

**Sonnet 5 pricing rises on 1 September 2026**, from $2/$10 to $3/$15 per MTok. If your
cost model was built on the current rate, re-run it before then. A 50% input increase
changes routing decisions.

The break-even is straightforward. A cached prefix pays for itself after roughly **1.5
reads** against the 5-minute write premium. Anything reused more than twice within the TTL
is unambiguously worth caching.

## Choosing a TTL

The 5-minute cache **refreshes for free** every time it is read. If your prompts are used
more often than every five minutes, stay on the default — you will never pay a second
write.

The 1-hour cache costs 2× base input on write. It is worth it when:

- Prompts are reused less often than every 5 minutes but more often than hourly
- A side-agent or long-running task will take more than five minutes
- A user may not reply within five minutes and you care about their time-to-first-token
- You want the rate-limit relief, since cache hits are not deducted against rate limits

Both TTLs behave identically for latency. And note the lifetime is measured from the
*start* of the request that writes or reads the entry, not the end of the response. If a
response streams for four minutes, a follow-up must start within about one minute.

## What invalidates the cache

The hierarchy is `tools → system → messages`. Changes at each level invalidate that level
and everything after it.

| Change | Invalidates |
|---|---|
| Tool definitions | Everything — tools, system, messages |
| Web search or citations toggle | System and messages |
| Speed setting | System and messages |
| `tool_choice` | Messages only |
| Adding/removing images anywhere | Messages only |
| Thinking parameters | Messages always; tools/system model-specific |
| Effort setting | Messages always; tools/system model-specific |

That first row is the one that hurts in MCP deployments: **any** change to a tool
definition — a name, a description, a parameter — invalidates the entire cache including
your system prompt. If you generate tool definitions dynamically, make sure the generation
is deterministic.

Which leads to the most obscure failure in this whole area: **non-deterministic JSON key
ordering**. Some languages, notably Go and Swift, randomise map key order during JSON
serialisation. If your `tool_use` blocks are serialised with unstable key ordering, the
prefix hash differs every request and you never get a hit. Everything looks correct in
your code. Enforce stable key ordering.

## Verifying it works

Three usage fields tell you everything:

```
total_input_tokens = cache_read_input_tokens
                   + cache_creation_input_tokens
                   + input_tokens
```

`input_tokens` counts **only** tokens after your last breakpoint — not your total input.
This trips people up when reconciling costs. A request with 100,000 cached tokens and a
50-token user message reports `cache_read_input_tokens: 100000` and `input_tokens: 50`.

A healthy steady-state pattern is a large `cache_read_input_tokens`, near-zero
`cache_creation_input_tokens`, and a small `input_tokens`. If `cache_creation` is
consistently large, your breakpoint is on something that varies.

There is also a cache diagnostics beta that has the API compare consecutive requests and
report exactly where the prefix diverged. When you are stuck, it will save you an hour of
bisecting.

## Pre-warming

You can load a prefix into the cache before real traffic arrives, using `max_tokens: 0`.
The API reads the prompt, writes the cache at your breakpoint, and returns immediately with
an empty `content` array and `stop_reason: "max_tokens"`. Zero output tokens are billed.

```python
client.messages.create(
    model="claude-opus-5",
    max_tokens=0,
    system=[{
        "type": "text",
        "text": "You are an expert software engineer with deep knowledge of distributed systems...",
        "cache_control": {"type": "ephemeral"},
    }],
    messages=[{"role": "user", "content": "warmup"}],
)
```

Two constraints matter. The breakpoint must sit on the block shared with your real
requests — typically the system prompt or tool definitions — **not** on the placeholder
user message. Put it on the placeholder and the entry is keyed to text your real traffic
never sends. This means using an explicit breakpoint rather than automatic caching, since
automatic caching places the breakpoint on the last block, which here is the placeholder.

And use the same thinking configuration and effort setting as your real requests. Those
values are rendered into the prompt, so a pre-warm with a different configuration writes
an entry your traffic will never hit.

`max_tokens: 0` is rejected with streaming, extended thinking, structured outputs, a
forced `tool_choice`, or inside a Message Batches request.

## The troubleshooting order

When the cache is not hitting, check in this sequence:

1. Are you above the minimum token count for your model?
2. Is the breakpoint on a block that is byte-identical across requests?
3. Are calls landing within the TTL, measured from request start?
4. Has a growing conversation pushed you past the 20-block lookback?
5. Are `tool_choice`, image presence, thinking config and effort stable between calls?
6. Are your `tool_use` blocks serialised with deterministic key ordering?
7. Have tool definitions changed — including regenerated ones that should be identical?

In our experience, items 2 and 4 account for most real-world cache misses, and item 6 for
most of the ones that take a full day to find.
