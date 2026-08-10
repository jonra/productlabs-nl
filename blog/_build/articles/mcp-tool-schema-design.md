---
title: Designing MCP tool schemas a model actually uses correctly
slug: mcp-tool-schema-design
dek: The model never sees your implementation. It sees a name, a description and a JSON Schema — and that is the entire interface. Most tool-calling failures are interface design problems wearing a model's clothes.
type: article
topic: mcp
date: 2026-07-12
updated: 2026-08-10
reading_time: 9
order: 3
meta_title: "Designing MCP Tool Schemas a Model Actually Uses Correctly"
meta_description: Tool naming, descriptions, parameter design and error messages — the schema decisions that determine whether a model calls your tool correctly.
keywords: [mcp tool design, mcp tool schema, llm tool description best practices, tool calling accuracy, json schema llm tools]
related: [mcp-tool-definition-token-cost, testing-debugging-mcp-servers, mcp-2026-07-28-migration-stateless-protocol]
---

When a tool call goes wrong, the instinct is to blame the model. Sometimes that is fair.
More often, we open the tool definition and find an interface no careful reader could use
correctly either.

The model never sees your implementation. It sees a name, a description and a JSON Schema.
That is the entire interface, and it is a *documentation* problem more than a code problem.

## Names carry meaning, so spend them

The name is the first and cheapest signal. Some rules that consistently help:

**Verb-object, not nouns.** `search_invoices` beats `invoices`. `create_ticket` beats
`ticket_handler`. The model is choosing an action; name the action.

**Namespace when tools coexist.** Any real deployment has several servers connected at
once. `search` is ambiguous across a document store, a CRM and a ticketing system.
`crm_search_contacts` is not. This matters more than it used to, because users routinely
run many servers simultaneously.

**Be specific about the object.** `get_data` tells the model nothing about when to use it.
`get_customer_invoice` tells it everything.

**Distinguish neighbours audibly.** If you have `update_record` and `upsert_record`, expect
confusion. Rename to `update_existing_record` and `create_or_update_record`. The extra
characters cost a few tokens; the mistake costs a wrong write.

## Descriptions should contain decision criteria

This is the highest-leverage change most tool definitions need.

Most descriptions define what the tool *is*. What the model needs is when to *use* it —
and, crucially, when not to.

Weak:

```
search_documents: Searches the document store.
```

Strong:

```
search_documents: Full-text search across the customer's uploaded documents.
Use when the user asks about the contents of a specific document, or asks a
question that document text would answer.

Do NOT use for: questions about document metadata such as upload date, owner
or file size — use list_documents for those. Do NOT use to retrieve a document
by ID — use get_document.

Returns up to 10 matching excerpts with document IDs. If more results are
needed, narrow the query rather than paginating.
```

The second version is longer, and every additional token is in every request. It is still
usually the right trade, because a wrong tool call costs a full round trip plus a recovery
attempt — dwarfing the token cost of a clear description. Measure this on your own
workload, but the default should be toward clarity.

Three elements do the work:

- **Use when** — the positive trigger, phrased the way a user would phrase the request
- **Do not use for** — explicit routing to the correct neighbouring tool
- **What comes back** — so the model can plan the next step rather than guessing

That middle element is the one almost nobody writes and the one that most reduces
misrouting.

## Parameter design

**Prefer flat over nested.** Deeply nested objects produce more malformed calls. If you
can express something as three top-level parameters instead of one nested object, do.

**Enums over free strings.** Any parameter with a known set of valid values should be an
enum. It constrains generation, it documents itself, and it turns a class of runtime
validation error into an impossible input.

```json
{
  "status": {
    "type": "string",
    "enum": ["draft", "sent", "paid", "overdue", "cancelled"],
    "description": "Invoice status to filter by. Omit to include all statuses."
  }
}
```

**Minimise required parameters.** Every required parameter is another thing the model must
correctly infer, often from an underspecified user request. If a sensible default exists,
make it optional and apply the default server-side.

**Describe every parameter, including obvious ones.** Especially formats. `date` is
ambiguous; "ISO 8601 date, e.g. 2026-06-30" is not. Ambiguous date and ID formats are one
of the most common sources of malformed arguments.

**Bound your numbers.** `minimum`, `maximum`, and a description saying what happens at the
limits. A `limit` parameter with no maximum invites a request for ten thousand records.

**Avoid boolean pairs that encode a mode.** `include_archived` plus `only_archived` is
three valid states expressed as four combinations, one nonsensical. Use a single enum.

## Errors are instructions

A tool error is not a failure report for a log file. It is the next thing the model reads,
and it determines what happens next. Write it as an instruction.

Weak:

```
Error: invalid request
```

Strong:

```
Error: 'start_date' must be ISO 8601 (YYYY-MM-DD). Received '30/06/2026'.
Retry with start_date="2026-06-30".
```

The strong version states what was wrong, what was received, and what to do. A model
reading it recovers on the next call. A model reading "invalid request" retries the same
malformed argument or gives up.

The pattern generalises:

- **Validation errors** — name the field, show the received value, give the correct form
- **Not found** — say so unambiguously, and suggest the tool that lists valid IDs
- **Permission denied** — distinguish "you cannot do this" from "you need to authenticate
  first", because the recovery differs completely
- **Rate limited** — say when to retry
- **Empty results** — an explicit "no results matched" beats an empty array, which reads as
  ambiguous

## Return shape

**Return what the next step needs, and not much else.** A tool that returns a full database
row when the model needs three fields spends context on every call. This compounds fast in
agent loops.

**Include identifiers.** If the model may need to act on a result, the result must carry
the handle. Search results without IDs force a second lookup.

**Summarise large results server-side.** If a query can return five hundred rows, return
the top ten plus a total count. The model cannot use five hundred rows and will pay for
all of them.

**Keep shapes stable.** A tool that sometimes returns an object and sometimes an array
produces unreliable downstream handling. Pick one.

**Say when there is more.** `"showing 10 of 47 matches"` lets the model decide whether to
narrow the query. A bare truncation looks like a complete answer.

## Tool count discipline

Every tool definition sits in the context window on every request. Beyond the token cost —
which is [its own article](/blog/mcp-tool-definition-token-cost/) — there is a selection
cost. More tools means more opportunity to pick the wrong one, and the marginal tool makes
every other tool slightly harder to choose correctly.

Two practices help:

**Consolidate variations into parameters.** `search_by_name`, `search_by_email` and
`search_by_phone` should be one `search_contacts` with a `field` enum.

**Split genuinely different operations.** Conversely, a single `manage_record` taking an
`action` parameter of `create`, `update` or `delete` hides a destructive operation behind a
benign name. Destructive actions deserve their own tools, both for clarity and so you can
scope permissions separately.

The tension between those two is real. The resolution: consolidate along dimensions that
do not change risk, split along dimensions that do.

## Testing the interface

You cannot evaluate a tool definition by reading it — you wrote it, so it is obvious to
you. Test it.

Build a set of realistic user requests, run them against your server, and record which
tool was called with which arguments. You are measuring two things: **selection accuracy**
(did it pick the right tool) and **argument accuracy** (were the arguments well-formed and
correct).

Run each case several times. Tool selection is non-deterministic, and a definition that
works four times out of five will look perfect in a single manual test and produce a
steady trickle of production failures.

When a case fails, resist patching the system prompt. The system prompt is a workaround
that has to be maintained forever and does not travel with your server to other clients.
Fix the definition — usually by adding a "do not use for" clause pointing at the tool that
should have been called.

## A checklist

- Name is verb-object, namespaced, and audibly distinct from its neighbours
- Description says **use when**, **do not use for**, and **what comes back**
- Every parameter has a description, including format for dates and IDs
- Known value sets are enums
- Required parameters are the minimum the tool genuinely cannot work without
- Numeric parameters have bounds
- Errors name the field, show the received value, and state the fix
- Returns include identifiers needed for follow-up actions
- Large results are summarised with a total count
- Destructive operations are separate tools, not an `action` parameter
- Selection and argument accuracy measured over repeated runs, not one manual try
