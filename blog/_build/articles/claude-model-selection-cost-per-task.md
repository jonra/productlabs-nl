---
title: Model selection is a cost-per-resolved-task problem, not a price-per-token one
slug: claude-model-selection-cost-per-task
dek: A model that costs a fifth as much but needs three attempts is not cheaper. Here is how to build the comparison that actually predicts your bill — and why Sonnet 5's September price change should send you back to it.
type: article
topic: claude-api
date: 2026-07-24
updated: 2026-08-10
reading_time: 10
badge_new: false
order: 6
meta_title: "Claude Model Selection: Cost Per Resolved Task, Not Per Token"
meta_description: Why per-token pricing misleads, how to measure cost per resolved task, routing patterns that work, and the Sonnet 5 price change landing 1 September 2026.
keywords: [claude opus vs sonnet vs haiku, claude api cost optimization, claude model selection, claude pricing comparison, model routing llm]
related: [claude-prompt-caching-guide, mcp-tool-definition-token-cost]
sources:
  - Claude Platform Docs — Prompt caching and model pricing|https://platform.claude.com/docs/en/build-with-claude/prompt-caching
---

<div class="callout">
<span class="callout-label">Pricing verified 10 August 2026</span>
<p>Claude Sonnet 5 pricing changes on 1 September 2026. If you are reading this after
that date, the second table below is the live one.</p>
</div>

Every few weeks someone shows us a spreadsheet comparing Claude models on price per
million tokens, with the cheapest option highlighted. It is the wrong comparison, and it
reliably produces the wrong decision.

Per-token price tells you what one attempt costs. It tells you nothing about how many
attempts you need.

## The arithmetic that matters

Consider a task where a cheaper model succeeds 60% of the time and a stronger one succeeds
95%, with a retry-once-then-escalate policy. The cheap model's *effective* cost includes
its failures, the retries, and the escalations those failures trigger. Once you add a
human reviewing the output of a failed automation, the per-token difference disappears
entirely — a few minutes of someone's time dwarfs the API spend on either model.

So the metric is:

```
cost per resolved task = (total API spend over a run)
                       / (number of tasks that met your acceptance bar)
```

Two things make this honest. **Total spend** must include failed attempts, retries, and
escalations. And **acceptance bar** has to be defined before you measure, not adjusted
afterwards to make a number look good.

That second point is where most internal comparisons quietly fall apart.

## Current pricing

Per million tokens:

| Model | Base input | Cache read | Output |
|---|---|---|---|
| Claude Fable 5 | $10 | $1 | $50 |
| Claude Opus 5 | $5 | $0.50 | $25 |
| Claude Opus 4.8 | $5 | $0.50 | $25 |
| Claude Sonnet 5 *(to 31 Aug 2026)* | $2 | $0.20 | $10 |
| Claude Sonnet 5 *(from 1 Sep 2026)* | $3 | $0.30 | $15 |
| Claude Sonnet 4.6 | $3 | $0.30 | $15 |
| Claude Haiku 4.5 | $1 | $0.10 | $5 |

Two observations before anyone builds a model on this.

**Sonnet 5 rises 50% on input and output on 1 September 2026.** Anyone who chose Sonnet 5
on price during its introductory window should re-run the comparison now. At $3/$15 it
sits at the same price as Sonnet 4.6, and the gap to Opus 5 narrows to less than 2×.

**Output tokens cost 5× input across the lineup.** For generation-heavy workloads, output
dominates. For analysis-heavy workloads with large context and short answers, input and
caching dominate. These two shapes have genuinely different optimal models, which is why a
single organisation-wide model choice is usually leaving money on the table.

## Building the comparison

You need an eval set. It does not need to be large — 50 to 100 real examples usually
separates models clearly enough to decide.

**Draw from production traffic.** Synthetic examples are systematically easier than real
ones, and they are easier in the specific way that flatters smaller models: cleaner input,
less ambiguity, fewer edge cases. Sample from real logs, including the ugly ones.

**Define acceptance mechanically where you can.** Exact match, schema validity, does the
generated code run and pass tests, does the extracted field match the ground truth. Where
the task is genuinely subjective, use a rubric and a fixed grader, and accept that your
error bars are wider.

**Record cost per attempt, not just per success.** You need the failures in the numerator.

**Run each model more than once.** These systems are non-deterministic. A single run
comparing two models can easily invert on a rerun. Three runs and a look at the variance
is the minimum before you make a routing decision on the result.

Then the table you actually want looks like this:

| | Resolution rate | Attempts per resolution | Cost per resolved task |
|---|---|---|---|
| Haiku 4.5 | measure | measure | compute |
| Sonnet 5 | measure | measure | compute |
| Opus 5 | measure | measure | compute |

We are deliberately not filling this in with numbers. Published benchmark figures for
"which model is cheaper" are close to meaningless across workloads — the answer depends
entirely on your task shape, your acceptance bar, and your prompt. The point of this
article is the method, and the method takes an afternoon to run on your own data.

## Routing patterns that work

**Cheap-first with escalation.** Try the smaller model, validate the output, escalate on
failure. Works well when validation is cheap and mechanical — schema checks, test suites,
constraint verification. Works badly when detecting failure requires the same judgement as
doing the task, because then you are paying for the strong model anyway.

The break-even is worth writing down:

```
escalation is worth it when:
    cost(small) + failure_rate × cost(large) < cost(large)
i.e. when:
    cost(small) < (1 - failure_rate) × cost(large)
```

At a 40% failure rate, the small model needs to cost less than 60% of the large one to be
worth trying first. Haiku against Opus 5 clears that comfortably. Sonnet 5 against Opus 5
after September — $3 against $5 — does not clear it at a 40% failure rate.

**Classifier routing.** Use a cheap model to triage difficulty, then dispatch. The
classification call is itself cheap and cacheable. The risk is that classification error
compounds with task error, so measure the classifier separately.

**Per-stage routing inside an agent loop.** This is where the largest wins usually are,
and it is underused. A single agent run contains steps with very different difficulty:
planning and synthesis are hard, while extraction, formatting, summarising a tool result
and deciding whether output matched a pattern are often easy. Routing per step rather than
per run frequently cuts cost substantially with no measurable quality change.

**Stage-gated escalation.** Start cheap, escalate only the specific step that failed,
rather than restarting the whole run on the stronger model. Requires your agent to be
checkpointed, which is worth doing anyway.

## Where cheaper models reliably win and lose

From deployments we have built, the pattern is consistent enough to be useful as a prior —
though you should still measure.

**Small models do well at:** structured extraction from clean input, classification into a
small label set, format conversion, summarising a single document, applying an explicit
rule you have written out in full, and routing decisions.

**Small models struggle with:** multi-step reasoning where an early error propagates,
tasks needing judgement about what is relevant, long-context synthesis across many
documents, generating code that must be correct rather than plausible, and any task where
the instructions are underspecified and the model must infer intent.

The mechanism behind that split is worth internalising: smaller models are relatively
weaker at knowing *when they are wrong*. In a pipeline with verification, that matters
less. In an autonomous loop, it compounds.

## Stack the other levers first

Model choice is one of three cost levers, and often not the biggest.

**Prompt caching** cuts input cost to 0.1× for the cached prefix. On a workload with a
large stable system prompt or tool set, this frequently beats downgrading the model — and
unlike a model downgrade it costs you nothing in quality. If you have not configured
caching properly, do that before you touch model selection.

**Batch processing** carries a discount for anything not latency-sensitive. Overnight
enrichment, backfills, evaluation runs.

**Prompt and tool trimming.** Every request carries your tool definitions. On a
multi-server MCP deployment that can be a substantial fixed cost per call before the user
has said anything.

These stack multiplicatively with each other. A cached, batched, trimmed Sonnet 5 call can
cost less than a naive Haiku call.

## A working method

1. Pull 50–100 real tasks from production logs, including the difficult ones.
2. Write a mechanical acceptance check, or a fixed rubric where you cannot.
3. Run each candidate model three times over the set.
4. Record spend including failures and retries; compute cost per resolved task.
5. Look at variance across runs before believing any gap.
6. Check whether caching or batching changes the ranking — it often does.
7. Identify the steps inside your pipeline that differ in difficulty, and route per step.
8. Re-run when pricing changes or a new model ships. Which, right now, means before
   1 September.

The reason to do this rather than reading someone else's benchmark is that the answer is
genuinely workload-specific. We have seen the same two models swap places between two
clients in the same industry, because one was doing extraction and the other was doing
synthesis. Your data is the only data that answers your question.
