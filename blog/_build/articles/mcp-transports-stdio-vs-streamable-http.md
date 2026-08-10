---
title: stdio or Streamable HTTP — choosing an MCP transport
slug: mcp-transports-stdio-vs-streamable-http
dek: There are two standard MCP transports, and SSE is not one of them any more. What each binding actually guarantees, how cancellation differs, and the deployment constraints that make the choice for you.
type: article
topic: mcp
date: 2026-08-01
updated: 2026-08-10
reading_time: 8
order: 4
meta_title: "stdio vs Streamable HTTP: Choosing an MCP Transport"
meta_description: The two standard MCP transports compared — framing, cancellation, credentials, and the deployment constraints that decide between stdio and Streamable HTTP.
keywords: [mcp transport, mcp stdio vs http, mcp streamable http, mcp sse deprecated, custom mcp transport]
related: [mcp-2026-07-28-migration-stateless-protocol, mcp-oauth-authorization-guide, mcp-tool-definition-token-cost]
sources:
  - MCP specification 2026-07-28 — Transports|https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
  - MCP specification 2026-07-28 — Authorization|https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
---

<div class="callout">
<span class="callout-label">Verified against the 2026-07-28 specification on 10 August 2026</span>
<p>A lot of material still frames this as "stdio vs SSE". HTTP+SSE is the deprecated
transport. The two standard bindings are stdio and Streamable HTTP.</p>
</div>

The first architectural decision on any MCP server is which transport to use, and it is
usually made in about four seconds by copying whatever the example did. Since it
determines your deployment model, your credential handling and your scaling story, it is
worth four minutes instead.

## A transport is a binding, not semantics

The specification is unusually clear about the separation, and it is the key idea:

> Protocol semantics are identical on every transport. A transport is a **binding**: it
> defines how messages are framed and delivered, how request metadata is carried, and how
> cancellation and termination are signaled. It does not define what the messages mean.

Message patterns are core protocol and identical everywhere. Tools behave the same. The
`_meta` model is the same. Your handler logic should not know or care which binding
carried the request.

If you find yourself writing transport-specific branching inside a tool implementation,
something has leaked that should not have.

Two constraints hold on every binding: messages are JSON-RPC and **must** be UTF-8
encoded; and only two message directions exist — client requests and notifications to the
server, server responses and notifications to the client. Servers do not initiate JSON-RPC
requests. Clients do not send responses.

## stdio

Newline-delimited JSON-RPC messages over the standard streams of a client-launched
subprocess.

The client launches your server as a child process and talks to it over stdin and stdout.
That is the whole mechanism, and its simplicity is the point.

**What it gives you:** no network stack, no ports, no TLS, no auth infrastructure. The
trust boundary is process launch — the client already decided to execute your binary, so
credential handling reduces to reading environment variables. The specification is explicit
that stdio implementations **should not** follow the OAuth authorization spec and should
retrieve credentials from the environment instead.

**Cancellation:** the client sends a `notifications/cancelled` notification.

**Where it fits:** local developer tooling, desktop client integrations, anything touching
the local filesystem, single-user tools, and prototypes. If your server reads local files
or drives local applications, stdio is almost certainly right.

**Where it does not:** anything multi-user, anything you want to update without shipping a
new binary to every user, anything that needs to scale horizontally.

One operational note: stdout is the message channel. Anything your process prints to
stdout that is not a protocol message corrupts the stream. Send logs to stderr. This is
the single most common way a new stdio server breaks, and the symptom — a parse error on
an apparently valid message — points nowhere near the cause.

## Streamable HTTP

Each message is an HTTP POST to a single MCP endpoint. Replies arrive either as a JSON
object or as a request-scoped SSE stream.

Note the shape: **one endpoint**, POST per message, and streaming scoped to an individual
request rather than a long-lived connection. Combined with the stateless model of the
current revision, a modern MCP server over Streamable HTTP is structurally an ordinary
HTTP service.

**Request metadata in headers.** All protocol metadata travels in the message body, but
this binding additionally mirrors selected fields into HTTP headers — notably
`MCP-Protocol-Version` — so intermediaries can route and inspect requests without parsing
the body. The body remains the source of truth, and the binding defines how mismatches
are rejected.

That mirroring is worth more than it first appears. It means a load balancer, API gateway
or WAF in front of your server can make routing and policy decisions on protocol version
without buffering and parsing every request body.

**Cancellation:** the client closes the request's response stream. Different mechanism
from stdio, same protocol-level semantics.

**Credentials:** OAuth 2.1, per the authorization specification — Protected Resource
Metadata, resource indicators, the full flow. This is real work, and it is the main cost
of choosing this binding.

**Where it fits:** multi-user and multi-tenant servers, anything that needs central
deployment and updates, anything behind a load balancer, anything integrating with systems
that already have HTTP auth infrastructure.

**Where it does not:** local filesystem access, single-user desktop tooling, or any case
where standing up authenticated infrastructure costs more than the integration is worth.

## The comparison

| | stdio | Streamable HTTP |
|---|---|---|
| Framing | Newline-delimited JSON-RPC over stdin/stdout | HTTP POST to one endpoint |
| Replies | Over stdout | JSON object or request-scoped SSE |
| Lifecycle | Client-launched subprocess | Ordinary HTTP request |
| Cancellation | `notifications/cancelled` | Close the response stream |
| Credentials | Environment | OAuth 2.1 |
| Metadata in headers | No | Yes, mirrored |
| Multi-user | No | Yes |
| Central updates | No | Yes |
| Infrastructure cost | None | TLS, auth, hosting |

## Choosing

The decision usually resolves on one question: **is there more than one user?**

If your server runs on one person's machine and touches that machine's resources, use
stdio. You will not need auth infrastructure, and the deployment story is "the client
launches it".

If multiple people use the same server instance, or you need to ship updates without
touching users' machines, use Streamable HTTP and accept the OAuth work.

The genuinely awkward middle case is a team-internal tool. It is multi-user, which points
at HTTP, but standing up an authorization server for six people is disproportionate. Two
reasonable resolutions: ship stdio and distribute the server through your existing package
tooling, or use HTTP behind your existing identity provider, since the spec builds on
standard OAuth 2.1 and any competent IdP already speaks it.

## Custom transports

Clients and servers **may** implement custom transports. The protocol is transport-agnostic
and works over any bidirectional channel.

If you do this, you **must** preserve the JSON-RPC message format, the message patterns,
and the per-request metadata model. And there is a specific piece of guidance worth
following:

> Custom transports that run over a reliable bidirectional byte stream (e.g., Unix domain
> sockets or TCP) **SHOULD** reuse the stdio framing rather than defining a new one.

The stdio binding is just newline-delimited JSON-RPC over a byte stream; only its
process-lifecycle rules are specific to standard streams. So a Unix-socket transport is
stdio framing with a different connection setup, and reusing it means existing parsers
work unchanged.

Custom transports should document connection establishment, message framing and
cancellation. In practice, the honest advice is: try hard to use a standard binding.
Custom transports work only with clients that implement them, and the ecosystem
compatibility cost usually outweighs whatever you were optimising.

## Practical guidance

Write your server so the transport is a thin outer layer. Handler logic takes a request
and returns a result, with no knowledge of framing. Then supporting both bindings is a
configuration decision rather than a rewrite, and testing gets substantially easier —
you can exercise handlers directly without a transport at all.

That separation also makes the migration path real. Plenty of servers start as stdio
developer tools and become team infrastructure a year later. If the transport is a
boundary, that transition is an afternoon. If it is threaded through your handlers, it is
a rewrite.
