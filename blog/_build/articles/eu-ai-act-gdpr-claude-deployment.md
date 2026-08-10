---
title: Deploying Claude in an EU company: what actually applies right now
slug: eu-ai-act-gdpr-claude-deployment
dek: The general-purpose AI grace period ended on 2 August 2026. Here is what now binds a company deploying Claude in the EU, what is still in motion, and what to do about it this quarter.
type: article
topic: compliance
date: 2026-08-04
updated: 2026-08-10
reading_time: 11
featured: true
badge_new: false
order: 10
featured_reason: The GPAI grace period expired on 2 August and Article 50 transparency duties are now live. Most compliance write-ups still describe the pre-August position. This one is dated, sourced, and honest about the part that is still moving.
meta_title: "EU AI Act & GDPR for Claude Deployments: August 2026 Status"
meta_description: What applies to EU companies deploying Claude after 2 August 2026 — GPAI enforcement, Article 50 transparency, penalties, GDPR overlap, and the high-risk deadline that is still in flux.
keywords: [eu ai act august 2026, ai act compliance netherlands, gdpr llm deployment, article 50 transparency, gpai obligations, ai act deployer obligations]
related: [prompt-injection-tool-using-agents, claude-model-selection-cost-per-task]
sources:
  - Timeline for implementation of the EU AI Act — European Commission AI Act Service Desk|https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act
  - EU AI Act Compliance Timeline: August 2026 Deadlines — Lyceum Technology|https://lyceum.technology/magazine/eu-ai-act-compliance-timeline-august-2026/index.html
  - The EU AI Act: What Actually Applies From August 2026 — Digital Applied|https://www.digitalapplied.com/blog/eu-ai-act-august-2026-transparency-obligations-agency-checklist
  - EU agrees to delay key AI Act compliance deadlines — Travers Smith|https://www.traverssmith.com/knowledge/knowledge-container/eu-agrees-to-delay-key-ai-act-compliance-deadlines/
  - Claude Platform Docs — Prompt caching and data retention|https://platform.claude.com/docs/en/build-with-claude/prompt-caching
---

<div class="callout">
<span class="callout-label">Verified 10 August 2026</span>
<p>This article describes the regulatory position as of its publication date, and one
significant element of it is still pending formal adoption. Regulatory timelines in
this area have moved repeatedly. Check the date above against today's before relying
on anything here, and treat this as background rather than legal advice — we build
software, we are not your counsel.</p>
</div>

If you deploy Claude inside an EU company, something changed this week and it is worth
understanding precisely what.

Obligations for general-purpose AI models have technically applied since 2 August 2025.
What ended on **2 August 2026** was the twelve-month grace period attached to them. From
that date the EU AI Office holds actual enforcement powers: it can request model access,
demand documentation, and issue fines. The transparency duties in Article 50 landed on
the same date.

For most companies reading this, the practical question is not "are we compliant with
the AI Act" in the abstract. It is narrower and more answerable: *which role do we
occupy, and what does that role owe?*

## First, work out which role you are in

The Act assigns obligations by role, not by company size, and the same organisation can
hold different roles for different systems.

**Provider** — you develop an AI system or general-purpose AI model and place it on the
market under your own name or trademark. If you build a product with Claude inside it and
sell that product, you are very likely a provider of that AI system, even though you did
not train the model.

**Deployer** — you use an AI system under your own authority in a professional capacity.
A company that uses Claude internally to triage support tickets or draft documents is a
deployer.

Most SMBs are deployers, and deployers carry a meaningfully lighter load than providers.
But the boundary is not where people assume. Two things commonly push a company across it:

- **Rebranding.** Putting your name on a Claude-powered assistant and offering it to
  customers generally makes you the provider of that system.
- **Substantial modification.** Materially changing an AI system's intended purpose can
  make you a provider of the modified system.

Anthropic is the provider of the underlying general-purpose model. That part is not your
obligation. What sits with you is the system you build around it and how you present it.

## What Article 50 transparency requires in practice

Article 50 is the part most likely to touch a normal software deployment, and it is
mercifully concrete. In broad terms it requires:

**Disclosure of AI interaction.** Where people interact with an AI system, they need to
be told, unless it is obvious from context to a reasonably well-informed person. A support
chat widget answering in natural language needs to say it is an AI. A spell-checker does not.

**Marking of synthetic content.** AI-generated or AI-manipulated audio, image, video and
text content needs to be marked as such in a machine-readable way, with exemptions where
the content has undergone human review and someone holds editorial responsibility.

**Disclosure for specific system types.** Emotion recognition and biometric categorisation
systems carry their own notification duties.

The engineering translation is short. If your product talks to people, say it is AI, in
the interface rather than buried in terms. If it generates content that leaves your
system, plan for provenance metadata. If you have a human editorial step, document it,
because it is what the exemption turns on.

## The penalty tier

GPAI and Article 50 violations sit in the same maximum tier under Article 99: the greater
of **€15 million or 3% of total worldwide annual turnover**. For a Dutch SMB, the
percentage is rarely the binding number, and €15 million is not a rounding error.

Worth stating plainly: the existence of a penalty ceiling is not a prediction that a
twenty-person company shipping a support bot will be fined. Enforcement attention will
concentrate where impact is greatest. But "unlikely to be enforced against us" is a risk
position, not a compliance position, and it is not one you want to discover you were
holding during a customer's security review.

## The part that is still moving

Here is where honesty matters more than confidence.

The original date for high-risk system obligations was **2 August 2026** — the same date
as everything above. The EU has agreed to push that deadline out to **December 2027**,
giving organisations substantially more room.

**That change is not yet formally adopted.** Until it is published in the EU Official
Journal, 2 August 2026 remains the binding date for high-risk obligations.

If you are anywhere near the high-risk classification — AI used in employment decisions,
credit scoring, education access, essential services, and the other Annex III categories —
this ambiguity is your most important open item. The pragmatic position is to plan against
the December 2027 timeline while documenting that you have done so deliberately, and to
watch for the Official Journal publication rather than assuming it has happened.

If you are not near high-risk, this uncertainty does not affect you, and the August 2026
GPAI and Article 50 position above is what governs.

## GDPR has not gone anywhere

The AI Act sits alongside the GDPR, and for most deployments the GDPR is the more
immediate constraint because it has fifteen years of enforcement behind it.

**Lawful basis.** Sending personal data to a model provider is processing, and it needs a
basis like any other. Legitimate interest is available but requires a balancing test you
can actually produce on request.

**Data minimisation in prompts.** This is the one engineering teams most reliably get
wrong. It is easy to stuff an entire customer record into context because the context
window allows it. Minimisation says send what the task requires. Practically: redact
before the call, not after; strip identifiers that play no role in the task; and be
deliberate about what goes into a system prompt that will be sent on every request.

**DPIA triggers.** A Data Protection Impact Assessment is required for processing likely
to result in high risk — systematic and extensive automated evaluation producing legal or
similarly significant effects, large-scale processing of special-category data, systematic
monitoring. Plenty of AI deployments trip one of these. Plenty do not. Assess rather than
assume in either direction.

**Processor relationships.** Your model provider is a processor. You need the agreement,
and you need to know where processing happens.

## Data residency and retention, concretely

Two implementation details that come up in every EU deployment conversation:

**Retention.** Zero data retention means the provider does not store the raw text of your
prompts or the model's responses. This is what makes a lot of deployments viable at all,
and it is worth confirming which features are ZDR-eligible for your specific configuration
rather than assuming blanket coverage.

**Caching.** Prompt caching is ZDR-eligible. Key-value cache representations and
cryptographic hashes of cached content are held in memory only, not stored at rest, and
entries have a minimum lifetime of five minutes or one hour depending on TTL before being
promptly deleted. Cache entries are isolated between organisations, and on the Claude API
they are isolated between workspaces within an organisation as well. That workspace-level
isolation is a useful control if you separate client work into workspaces — worth knowing
that Bedrock and Google Cloud use organisation-level isolation only, which is a different
posture.

**Processing location.** If data residency is a contractual requirement for you, this is a
platform selection question that needs answering before you build, not after. Retrofitting
a residency requirement into a working integration is expensive.

## A checklist for this quarter

If you are a deployer running Claude inside an EU company, working through this list will
put you in a defensible position:

1. **Write down your role** for each AI system you run. Provider, deployer, or both.
   One line each. This determines everything downstream.
2. **Inventory your AI systems.** You cannot classify what you have not listed. Include
   the shadow deployments — someone's departmental automation counts.
3. **Add AI disclosure** anywhere a person interacts with a model. Interface-level, not
   buried in terms.
4. **Assess high-risk exposure** against Annex III. If you are close, track the Official
   Journal for the December 2027 amendment rather than assuming it has landed.
5. **Confirm your lawful basis** for personal data reaching the model, and write down the
   balancing test if you are relying on legitimate interest.
6. **Audit prompt contents** for data minimisation. Look specifically at system prompts
   and retrieved context, which are the usual offenders.
7. **Determine whether a DPIA is required**, and do it if so.
8. **Check your processor agreement** and confirm the retention and residency posture
   matches what you have told customers.
9. **Turn on logging** sufficient to reconstruct what a system did and why. Both regimes
   assume you can answer that question.
10. **Set a review date.** This area is moving. A compliance position with no review date
    decays into a liability.

## The honest summary

For a typical Dutch SMB deploying Claude for internal knowledge work, the August 2026
change is real but manageable: enforcement powers are now live, transparency duties apply,
and the GDPR obligations you already had are unchanged. The genuinely uncertain item is
the high-risk deadline, and it only matters if you are near that classification.

The failure mode we see most often is not a company getting a rule wrong. It is a company
that never wrote down which role it occupies, and therefore cannot answer any of the
downstream questions when a customer, an auditor or a regulator asks. That document takes
an afternoon.
