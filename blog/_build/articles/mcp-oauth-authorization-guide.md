---
title: OAuth for remote MCP servers, as the spec defines it today
slug: mcp-oauth-authorization-guide
dek: Most guides tell you to implement Dynamic Client Registration. The current specification marks it deprecated. Here is the authorization flow MCP actually requires now — discovery, registration, resource indicators and issuer validation.
type: article
topic: mcp
date: 2026-08-06
updated: 2026-08-10
reading_time: 12
order: 8
meta_title: "OAuth for Remote MCP Servers: A Current Implementation Guide"
meta_description: MCP authorization as the 2026-07-28 spec defines it — Protected Resource Metadata, Client ID Metadata Documents, RFC 8707 resource indicators, and RFC 9207 issuer validation.
keywords: [mcp oauth, mcp authorization, mcp server authentication, protected resource metadata, client id metadata documents, rfc 8707 resource indicator]
related: [mcp-2026-07-28-migration-stateless-protocol, mcp-transports-stdio-vs-streamable-http, prompt-injection-tool-using-agents]
sources:
  - MCP specification 2026-07-28 — Authorization|https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
  - RFC 9728 — OAuth 2.0 Protected Resource Metadata|https://datatracker.ietf.org/doc/html/rfc9728
  - RFC 8707 — Resource Indicators for OAuth 2.0|https://www.rfc-editor.org/rfc/rfc8707.html
  - RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification|https://datatracker.ietf.org/doc/html/rfc9207
---

<div class="callout">
<span class="callout-label">Verified against the 2026-07-28 specification on 10 August 2026</span>
<p>MCP's authorization chapter has changed materially between revisions. Several
widely-shared implementation guides now describe a deprecated registration mechanism.
Check the current spec before shipping.</p>
</div>

If you search for how to authenticate an MCP server, most of what you will find tells you
to implement Dynamic Client Registration. The current specification marks DCR
**deprecated**, retained only for backwards compatibility with authorization servers that
do not support the mechanism that replaced it.

That is the headline correction. There are several others. Here is the flow as the
`2026-07-28` revision actually defines it.

## When authorization applies at all

Authorization is **optional** for MCP implementations. When you do implement it:

- HTTP-based transports **should** conform to the authorization specification.
- **stdio transports should not.** A stdio server is a subprocess launched by the client;
  it retrieves credentials from the environment. Bolting OAuth onto stdio is a category
  error — the trust model is already established by process launch.
- Alternative transports must follow established security practice for their protocol.

So this article is about remote servers. If you are shipping a local stdio tool, read an
environment variable and move on.

## The role mapping

MCP maps cleanly onto OAuth 2.1 roles, and getting the mapping straight makes the rest
follow:

- A protected **MCP server** is an OAuth 2.1 **resource server**.
- An **MCP client** is an OAuth 2.1 **client**.
- The **authorization server** issues tokens. It may be hosted with the resource server or
  be an entirely separate entity — the spec deliberately leaves its implementation out of
  scope.

The specification builds on OAuth 2.1 plus a selected subset of related RFCs. It is not a
bespoke auth scheme, which means you can use existing OAuth infrastructure. What it adds
is a set of hard requirements about discovery and audience binding.

## Discovery is mandatory, in both directions

This is where implementations most often fall short of the spec.

**MCP servers must implement OAuth 2.0 Protected Resource Metadata (RFC 9728).** Clients
**must** use it for authorization server discovery. This is not optional on either side.

The flow starts with an unauthenticated request. Your server responds `401` with a
`WWW-Authenticate` header pointing at the metadata document:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource",
                         scope="files:read"
```

The client fetches that document, extracts the authorization server, and then discovers
the authorization server's own metadata.

**Authorization servers must provide at least one of** OAuth 2.0 Authorization Server
Metadata (RFC 8414) or OpenID Connect Discovery 1.0. **Clients must support both**,
trying the discovery endpoints in priority order. You do not get to pick one and ignore
the other on the client side.

## Client registration, in priority order

Before starting the flow, a client needs a client ID. The specification defines three
mechanisms and a clear preference order:

1. **Client ID Metadata Documents** — authorization servers and clients **should** support
   this. The client uses an HTTPS URL as its `client_id`; the authorization server detects
   the URL form, fetches the metadata document from it, and validates the metadata and
   redirect URIs.
2. **Pre-registration** — use an existing `client_id` you were issued out of band.
3. **Dynamic Client Registration (RFC 7591)** — **may** be supported, and is **deprecated**.
   It exists for authorization servers that do not yet support Client ID Metadata Documents.

If you are writing a new client today, implement Client ID Metadata Documents first and
treat DCR as the compatibility fallback. That is the inverse of what most existing guides
recommend, and it is the change most likely to bite anyone copying an older implementation.

## The resource parameter is not optional

MCP clients **must** implement Resource Indicators for OAuth 2.0 (RFC 8707). The
`resource` parameter:

- **must** appear in both the authorization request and the token request,
- **must** identify the MCP server the token is intended for,
- **must** use the canonical URI of that server.

And critically: clients **must** send it regardless of whether the authorization server
supports it.

This is the mechanism that stops a token issued for one MCP server being replayed against
another. It is the backbone of the spec's audience-binding model, and skipping it because
"our AS ignores it anyway" defeats the protection for every server that does check.

The canonical URI rules cause real bugs, so they are worth memorising:

**Valid:** `https://mcp.example.com/mcp`, `https://mcp.example.com`,
`https://mcp.example.com:8443`, `https://mcp.example.com/server/mcp` where the path is
needed to identify an individual server.

**Invalid:** `mcp.example.com` (no scheme), `https://mcp.example.com#fragment` (fragments
are not allowed).

Use the most specific URI you can. Prefer the form without a trailing slash unless the
slash is semantically significant. Clients should send lowercase scheme and host, but
implementations should accept uppercase for robustness.

```
&resource=https%3A%2F%2Fmcp.example.com
```

## Issuer validation, and the normalisation trap

Before redirecting the user agent, the client **must** record the `issuer` value from the
selected authorization server's validated metadata, stored alongside the PKCE code
verifier for that request. The validation that follows is worthless if the expected issuer
came from an unvalidated source.

Authorization servers **should** include the `iss` parameter in authorization responses,
including error responses, and advertise this by setting
`authorization_response_iss_parameter_supported` to `true` in their metadata.

On receiving the authorization response, the client must validate before sending the code
to any token endpoint:

| `..._iss_parameter_supported` | `iss` present? | Client action |
|---|---|---|
| `true` | yes | Compare against recorded issuer |
| `true` | no | **Reject** |
| `false` or absent | yes | Compare against recorded issuer |
| `false` or absent | no | Proceed |

The third row is deliberate: compare a present `iss` regardless of what the metadata
advertised, to accommodate servers that started emitting `iss` before updating their
metadata document.

Now the trap. After decoding the `iss` value from the form-encoded response, clients
**must not** apply scheme or host case folding, default-port elision, trailing-slash
normalisation, or percent-encoding normalisation before comparing. Simple string
comparison, nothing else.

If you reach for a URL library here, it will helpfully normalise the value and you will
have silently weakened the check. Compare the raw decoded strings.

This validation applies to error responses too — on mismatch, the client must not act on
or even display `error`, `error_description` or `error_uri`. An attacker-controlled error
description rendered in your UI is a phishing surface.

## Scopes, and asking for the right ones

Servers **should** include a `scope` parameter in the `WWW-Authenticate` challenge to
indicate what the resource needs. Clients should follow least privilege:

1. Use the `scope` from the initial `WWW-Authenticate` header if provided.
2. Otherwise use `scopes_supported` from the Protected Resource Metadata, omitting `scope`
   entirely if that field is undefined.

The challenged scope set has no guaranteed relationship to `scopes_supported` — it may be
a subset, a superset, or neither. Clients **must not** assume one and **must** treat the
challenge as authoritative for the current operation. `scopes_supported` is intended to
represent the minimal set needed for basic functionality, with more requested
incrementally.

## Step-up authorization

When a client has a token but needs more permission, the server should respond:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                         scope="files:write",
                         resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource",
                         error_description="File write permission required for this operation"
```

The client then:

1. Parses the error information.
2. Computes the **union** of its previously requested scopes and the challenged scopes.
   This is the step people miss — servers are not required to include previously granted
   scopes in the challenge, so requesting only the challenged scope can silently drop
   permissions the client still needs.
3. Re-authorizes with that union.
4. Retries the original request, no more than a few times, then treats it as permanent
   failure.

On the server side: include **all** scopes required for the current operation in a single
challenge. Challenging incrementally — one missing scope, then another on retry — forces
multiple authorization round trips for one operation and produces a genuinely unpleasant
user experience. Be consistent about your strategy, and account for scope hierarchies
where a broader scope implies narrower ones.

## Token handling: the rules that matter most

Three requirements carry most of the security weight, and all three are absolute:

**Audience validation.** Servers must validate that access tokens were issued specifically
for them as the intended audience. A token that is valid but was minted for a different
resource must be rejected.

**No token forwarding.** Servers must only accept tokens valid for their own resources,
and **must not accept or transit any other tokens**. If your MCP server takes a token and
passes it downstream to another API, you have built a confused deputy.

**No tokens in URLs.** Access tokens go in the `Authorization: Bearer` header, on every
request, and must not appear in the query string.

Error responses are conventional: `401` for missing or invalid tokens, `403` for
insufficient scope, `400` for a malformed request.

## Refresh tokens

A small detail with a practical consequence: MCP servers acting as protected resources
**should not** include `offline_access` in the `WWW-Authenticate` scope or in
`scopes_supported`. Refresh tokens are not a resource requirement — they are a
client–authorization-server concern.

Clients that want refresh tokens should include `refresh_token` in their `grant_types`
metadata, may add `offline_access` to the scope when the authorization server advertises
it, and must not assume refresh tokens will be issued at all. The authorization server
retains discretion.

## Implementation checklist

**Server side**

- Serve a Protected Resource Metadata document at the well-known path
- Return `401` with `resource_metadata` and a `scope` hint
- Validate token audience against your canonical URI, and reject anything else
- Never forward a received token to another service
- Return `403` with `insufficient_scope` and the complete required scope set
- Keep `offline_access` out of your advertised scopes

**Client side**

- Use Protected Resource Metadata for discovery — do not hardcode endpoints
- Support both RFC 8414 and OIDC discovery
- Prefer Client ID Metadata Documents; fall back to DCR only when necessary
- Send `resource` on both authorization and token requests, always
- Record the expected issuer with the PKCE verifier, and compare raw strings
- Compute the scope union on step-up
- Cap retries and track scope upgrade attempts per resource and operation

## The short version

MCP authorization is OAuth 2.1 with three additions that carry the security model:
mandatory metadata-based discovery, mandatory resource indicators for audience binding,
and strict issuer validation with no normalisation. Get those three right and the rest is
ordinary OAuth. Get them wrong and you have built something that looks like OAuth and
protects considerably less.
