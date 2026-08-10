---
title: MCP without initialize — migrating to the 2026-07-28 revision
slug: mcp-2026-07-28-migration-stateless-protocol
dek: The current MCP revision removes the initialize handshake entirely. Servers are stateless, every request carries its own protocol version, and most of the MCP material on the internet now describes a legacy protocol.
type: article
topic: mcp
date: 2026-07-29
updated: 2026-08-10
reading_time: 10
badge_new: false
order: 9
meta_title: "MCP Without initialize: Migrating to the 2026-07-28 Revision"
meta_description: The 2026-07-28 MCP revision drops the initialize handshake and makes servers stateless. What changed, what breaks, and how to build a server that serves both eras.
keywords: [mcp 2026-07-28, mcp initialize deprecated, mcp protocol version negotiation, mcp legacy vs modern, server/discover, UnsupportedProtocolVersionError]
related: [mcp-transports-stdio-vs-streamable-http, mcp-oauth-authorization-guide, testing-debugging-mcp-servers]
sources:
  - MCP specification 2026-07-28 — Versioning and Compatibility|https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
  - MCP specification 2026-07-28 — Transports|https://modelcontextprotocol.io/specification/2026-07-28/basic/transports
---

<div class="callout">
<span class="callout-label">Verified against the 2026-07-28 specification on 10 August 2026</span>
<p>MCP revisions have changed the protocol's shape more than once. If you are reading
this well after the date above, check the current specification before implementing.</p>
</div>

If you learned MCP from a tutorial, a conference talk, or an SDK example, there is a good
chance you learned a protocol that the current specification calls **legacy**.

The `2026-07-28` revision removes the `initialize` handshake. There is no negotiation
step, no connection-scoped session, and servers no longer initiate JSON-RPC requests.
Every request carries its own protocol version, and the server accepts or rejects each
one independently.

This is not a cosmetic change. It alters how you write a server, how you write a client,
and what "connected" even means.

## What actually changed

The specification's own terminology is the clearest way in:

- **Modern** — protocol versions that convey version, identity and capabilities as
  per-request metadata. Revision `2026-07-28` and later.
- **Legacy** — protocol versions that establish a session with an `initialize`
  handshake. Revision `2025-11-25` and earlier.
- **Dual-era** — an implementation supporting both.

Three concrete consequences follow.

**There is no negotiation handshake.** Every request declares its protocol version in its
`_meta` field. The server either supports that version and answers, or rejects that
request. Nothing is agreed up front.

**Servers are stateless by default.** Because there is no session, a modern request is
served on its own terms. This is a significant simplification for horizontally scaled
deployments — no session affinity, no shared session store, no reconnection dance.

**Message direction is constrained.** Servers do not initiate JSON-RPC requests, and
clients do not send JSON-RPC responses. A binding delivers client requests and
notifications to the server, and server responses and notifications to the client. That
is the entire set of directions. If your design assumed a server could call back into the
client mid-session, that assumption no longer holds in the core protocol.

## Per-request metadata

Protocol metadata travels in the message body. Every request carries its protocol version
and client capabilities in `_meta.io.modelcontextprotocol/*` fields.

On Streamable HTTP, the version is additionally mirrored into an `MCP-Protocol-Version`
header, so that proxies and gateways can route and inspect requests without parsing the
body. The body remains the source of truth; the binding defines how mismatches are
rejected.

That mirroring is worth noticing if you run anything in front of your MCP server. It is
the difference between a load balancer that can route by protocol version and one that
has to buffer and parse every request.

## Version rejection and retry

When a server does not implement the requested version — whether it is unknown to the
server, or a known version the server has chosen not to support — it must respond with
`UnsupportedProtocolVersionError`, listing what it does support:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32022,
    "message": "Unsupported protocol version",
    "data": {
      "supported": ["2026-07-28", "2025-11-25"],
      "requested": "1900-01-01"
    }
  }
}
```

The client should then select a mutually supported version from `supported` and retry, or
surface an actionable error if there is no overlap.

This is the single most important behaviour to get right on both sides. A client that
treats `-32022` as a generic failure will present users with an opaque error when the fix
was mechanical. A server that returns a bare error without the `supported` list leaves
clients with nothing to retry against.

## server/discover

Servers **must** implement `server/discover`. Clients **may** call it before sending
anything else to learn the server's supported versions up front — but they are not
required to. A client is free to invoke any RPC inline and handle
`UnsupportedProtocolVersionError` if its preferred version is not supported.

That "may" is doing real work. It means `server/discover` is a diagnostic and
optimisation tool, not a replacement handshake. Do not rebuild `initialize` out of it by
requiring a discover call before every session — that reintroduces exactly the round trip
the revision removed.

Where it genuinely earns its place is era detection, which is the next problem.

## Interoperating with legacy implementations

You will be talking to legacy implementations for a long time. The specification defines
the compatibility surface precisely, and the results are asymmetric:

| Client | Server | Outcome |
|---|---|---|
| Modern | Modern | Works |
| Modern | Legacy | **Fails** |
| Dual-era | Modern | Works |
| Dual-era | Legacy | Works |
| Legacy | Modern | **Fails** |
| Legacy | Dual-era | Works |
| Legacy | Legacy | Works, per the legacy revision |

Two rows deserve attention.

**Modern client, legacy server fails**, and it can fail badly. The server may reject the
request with an implementation-defined error, stay silent, or — worst case — process an
era-ambiguous method under legacy semantics. On stdio, clients should send
`server/discover` first specifically so this fails deterministically rather than
ambiguously.

**Legacy client, modern server fails with no recovery.** Legacy clients have no
fall-forward mechanism. This is why the specification says a modern-only server *should*
name the protocol versions it supports in any error it returns to an `initialize` request,
on any transport. That error message may be the only diagnostic a legacy client can put
in front of a user. It costs you three lines and saves someone an afternoon.

## Detecting a server's era

Era is a property of the server, not of an individual request. Detect it once, cache it
for the lifetime of the server process (stdio) or origin (HTTP), and optionally persist it
across restarts of the same configuration — re-probing if the cached assumption later
fails.

The mechanics are transport-specific:

**stdio** — probe with `server/discover` and fall back to legacy on any error that is not
a recognised modern error.

**Streamable HTTP** — attempt a modern request and inspect the body of a `400 Bad Request`
before falling back.

In both cases the rule is the same: a recognised modern JSON-RPC error such as
`UnsupportedProtocolVersionError` identifies a *modern* server. The client should then
retry with a supported version rather than falling back to legacy. Anything else — an
unrecognised error, silence, a timeout — identifies a legacy server.

That distinction is the one implementations get wrong. `UnsupportedProtocolVersionError`
is not a failure signal, it is a success signal about the server's era carrying a
correction about the version.

```python
MODERN_ERROR_CODES = {-32022}  # UnsupportedProtocolVersionError

def detect_era_stdio(conn) -> str:
    """Probe once, per server process. Cache the answer."""
    try:
        result = conn.request("server/discover")
    except JsonRpcError as e:
        # A recognised modern error still means the server is modern —
        # it is telling us which versions it speaks.
        return "modern" if e.code in MODERN_ERROR_CODES else "legacy"
    except (TimeoutError, TransportError):
        return "legacy"
    return "modern" if result is not None else "legacy"
```

## Building a dual-era server

A server that wants to serve both eras may implement both behaviours, and may serve them
concurrently on the same endpoint or process. It selects behaviour from how the client
opens:

- A request carrying modern per-request `_meta` is served statelessly, per the current
  revision.
- An `initialize` request selects legacy semantics, scoped to the stdio process or the
  HTTP session, per the negotiated legacy protocol version.

The design implication is that your handler logic should not assume session state exists.
Write the tool implementations against a stateless model, then let the legacy path
maintain whatever session bookkeeping the older revision requires around them. Doing it
the other way round — building on session state and trying to fake it for modern requests —
produces a server that is hard to scale and hard to reason about.

## Extensions replace capability sprawl

Optional functionality beyond the core protocol is negotiated through an `extensions` map
in capabilities: extension identifiers mapped to per-extension settings objects.
Identifiers must follow the `_meta` key naming rules, including a mandatory prefix.

```json
{
  "capabilities": {
    "tools": {},
    "extensions": {
      "io.modelcontextprotocol/tasks": {}
    }
  }
}
```

An empty settings object means "supported, no additional settings". If one party supports
an extension and the other does not, the supporting party must either revert to core
protocol behaviour or reject the request with an appropriate error — and extensions should
document which of those they expect.

The practical guidance: build on the core protocol, treat every extension as optional, and
make sure your fallback path is tested rather than theoretical.

## Migration checklist

If you have an existing MCP server:

1. **Decide your era support.** Modern-only is simpler. Dual-era is what you need if you
   have users on older clients you do not control.
2. **Remove session assumptions** from tool handlers. Anything stored between calls needs
   an explicit home.
3. **Implement `server/discover`.** It is mandatory, and it is what well-behaved clients
   probe with.
4. **Return proper `UnsupportedProtocolVersionError`** responses with a populated
   `supported` list.
5. **If modern-only, name your supported versions** in the error you return to
   `initialize`. Legacy clients cannot recover, but their users can at least be told why.
6. **Read `_meta` for the protocol version**, and on HTTP decide how you handle a
   mismatch between the header and the body.
7. **Audit for server-initiated requests.** If you had any, they need redesigning.
8. **Test the era matrix**, not just the happy path. Both failing combinations should fail
   in the way the specification describes.

## Why this is worth doing now

The stateless model is a genuine simplification. A modern MCP server is closer to an
ordinary HTTP service than to a stateful protocol daemon: no session store, no affinity
requirement, no reconnection semantics. That makes it dramatically easier to deploy behind
a normal load balancer and to reason about under load.

The cost is a migration window where the ecosystem is split, and a large body of
documentation, tutorials and example code that is now describing the previous protocol
without saying so. When you hit a discrepancy between a blog post and the specification,
the specification is right and the blog post is probably just older than July.
