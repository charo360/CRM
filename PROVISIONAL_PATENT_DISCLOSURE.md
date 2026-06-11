# Provisional Patent Application — Technical Disclosure

**Working title:** *Systems and Methods for a Trust-Gated, Relationship-Aware Autonomous AI Operations Agent*

**Applicant / Inventor:** [YOUR FULL LEGAL NAME]
**Date prepared:** 2026-06-01
**Status:** DRAFT for USPTO provisional filing (not examined; establishes priority date)

> **How to use this document.** This is the "specification" (written description) for a US provisional patent application. A provisional is not examined — its job is to describe the invention thoroughly enough that a later non-provisional application can claim priority to today's date. **Everything you want protected must be described here**; anything left out is not covered by the early date. Fill every `[BRACKETED]` placeholder, attach the diagrams listed in §10, complete USPTO form SB/16, and file via patentcenter.uspto.gov.
>
> ⚠️ **File before any public launch** (Chrome Web Store listing, public demo, paid sale). Public disclosure starts a 12-month clock in the US and *immediately destroys* patent rights in most other countries.

---

## 1. Field of the Invention

This invention relates to artificial-intelligence software agents, and more specifically to a multi-agent system in which an AI operations agent (a) earns delegated authority through an auditable, event-sourced "trust ladder," (b) develops a persona whose communication style evolves as a function of relationship duration, (c) autonomously performs business-operations work and reports it through a deterministically-ranked daily briefing, and (d) maintains a continuously re-indexed semantic memory of meetings and notes.

## 2. Background and Problem

Existing AI assistants and "copilots" suffer from several unsolved problems:

1. **Trust is binary and unaccountable.** A user either turns an agent's autonomy on or off. There is no graduated, per-domain mechanism by which an agent *earns* the right to act unsupervised, and no audit trail explaining *why* it has the authority it has.
2. **No delegation chain.** When an agent itself coordinates sub-agents, there is no enforceable mechanism ensuring a sub-agent cannot be granted authority except through a human-ratified recommendation.
3. **Static persona.** Assistant tone is fixed. It does not reflect the growing history between the user and the agent, so it cannot build the sense of an evolving working relationship.
4. **Notification overload.** Agents surface everything they do, or hide everything. There is no principled, deterministic method for selecting the *few* items that genuinely require human attention.
5. **Stale semantic memory.** When a user edits meeting notes, vector-search indexes built from the original text become inconsistent with the edited content.

The system described here addresses each problem with specific technical mechanisms.

## 3. Summary of the Invention

The invention is a system comprising several independently novel sub-mechanisms that may be claimed separately or in combination:

- **(A) Event-sourced trust-ladder engine** that computes, by deterministic replay of an append-only event log, a per-(actor, category) "rank" governing how much autonomy an AI agent has in a given operational domain, subject to enforced invariants including a human-ratified delegation chain and automatic probation on demotion.
- **(B) Relationship-duration persona evolution** that selects the agent's writing-voice calibration as a function of elapsed relationship days, advancing through discrete phases.
- **(C) Deterministic synthesized reflective journal** that generates at most one human-readable reflective entry per day from the trust-event log, written in the current persona phase, by selecting a single dominant event per day.
- **(D) Deterministic briefing ranker and validated letter composer** that scores candidate actions on a weighted combination of urgency, importance, confidence, and freshness, caps the surfaced set, and emits a voice- and shape-validated briefing snapshot.
- **(E) Voice-validated agent memory ("notebook")** with asymmetric validation (agent-authored writes are style-validated; human edits bypass validation) feeding relevance-ranked citations into the briefing.
- **(F) Edit-synchronized semantic re-indexing of meeting notes**, in which any edit to a note triggers deletion of prior embedding chunks and re-embedding of the edited content as a non-blocking background task, keeping semantic search consistent with user edits.

Each is described in detail below. The combination — an agent that *earns* domain-specific autonomy on an auditable ladder, *narrates its own growth* in an evolving voice, and *reports* through a disciplined daily ritual — constitutes the overall system.

---

## 4. Mechanism A — Event-Sourced Trust-Ladder Engine

### 4.1 What it is

A method for governing AI-agent autonomy in which the agent's authority is not a stored flag but a **pure function of an append-only log of trust events**. Authority is tracked independently for each combination of *actor* (the chief agent or a named sub-agent) and *category* (an operational domain such as replies, invoices, follow-ups, leads). The current authority — a "Standing" comprising a discrete **rank** and a boolean **probation** state — is obtained by replaying every event in order through a single state-mutation function.

### 4.2 Why it is novel

Authority is **per-domain and earned**, **fully reconstructible** from the log (the state is derivable, never authoritative on its own), and constrained by **enforced trust-chain invariants**. In particular, a sub-agent's rank can only increase through a human approval event that is cryptographically/logically *chained* to a prior matching recommendation event emitted by the chief agent — the system rejects any approval that does not reference a still-pending, exactly-matching recommendation.

### 4.3 Detailed operation

1. The system maintains an append-only event store of typed trust events. Event types include, without limitation: user-promotes-chief-agent, user-demotes-chief-agent, chief-agent-recommends-sub-agent-promotion, user-approves-recommendation, user-denies/defers-recommendation, chief-agent-demotes-sub-agent, chief-agent-lifts-probation, and a class of *operational* events (action approved, clean send, action rejected, action undone, mistake flagged).
2. State is a map keyed by (actor, category) → Standing(rank, on_probation). Any (actor, category) never seen defaults to the lowest rank ("Observer") and not on probation.
3. A single mutator applies one event to state and **enforces invariants**, raising an error that aborts the application if any is violated:
   - Only a user-promotion event may raise the chief agent's rank; the declared `from_rank` must equal the current rank, and `to_rank` must be strictly greater (strictly lower for demotion).
   - A sub-agent's rank may rise **only** via a user-approval event carrying a `recommendation_id` that matches a *still-pending* recommendation whose actor, category, from_rank, and to_rank all match exactly, and whose subject's current rank is unchanged since the recommendation was made. Otherwise the approval is rejected.
   - The chief agent may unilaterally demote a sub-agent; any demotion sets probation true automatically.
   - Probation is cleared only by an explicit lift-probation event, never as a side effect of promotion.
   - Operational events change the log but never directly change rank; they are consumed downstream by a separate trust-score calculator.
4. Because state = replay(log), the system can answer "why does this agent have this authority?" by exhibiting the exact event subsequence that produced the current Standing — an auditable explanation impossible in flag-based designs.

### 4.4 Claimable points

- A method for granting AI-agent autonomy on a per-(actor, domain) basis as a deterministic replay of an append-only trust-event log.
- A delegation-chain invariant whereby a sub-agent's authority can increase only through a human approval event logically chained to a matching, still-pending recommendation event.
- Automatic probation-on-demotion with explicit, separate probation lift.

---

## 5. Mechanism B — Relationship-Duration Persona Evolution

### 5.1 What it is

A method for selecting an AI agent's communication-style configuration ("voice calibration") as a function of the integer number of days since the user-agent relationship began. The day count maps to one of several ordered phases (e.g., Observing → Shifting → Blended → Earned → Perspective), each carrying a distinct style directive, a worked example, and a soft word ceiling that the prompt builder injects into the language-model system prompt.

### 5.2 Why it is novel

The agent's tone is **a function of relationship tenure**, advancing through discrete, bounded phases — producing the experience of an agent that visibly *matures* over weeks and months. Critically, **only the reflective/journal voice evolves**; the operational voice (briefings, confirmations) is held constant — a deliberate split between an evolving "inner" voice and a stable "working" voice.

### 5.3 Detailed operation

1. Each phase is defined by a day range, a style directive string, an example, and a target word ceiling.
2. A pure function maps a day count to its phase's calibration (days below 1 clamp to the first phase; days above the last boundary resolve to the final phase).
3. The selected directive is injected verbatim into the model prompt for entries governed by the evolving voice.

### 5.4 Claimable points

- Selecting an AI agent's generative style configuration as a function of relationship-tenure days mapped to ordered phases.
- Bifurcating the agent's voice so that only the reflective channel evolves while the operational channel is held constant.

---

## 6. Mechanism C — Deterministic Synthesized Reflective Journal

### 6.1 What it is

A method that generates, for each calendar day, at most one short first-person reflective "journal" entry attributed to the AI agent, derived from that day's trust events and rendered in the agent's current relationship-phase voice. Entries are deterministic: the same inputs always produce the same entry, with stable identifiers keyed by (kind, day) so an entry is never duplicated within a day.

### 6.2 Why it is novel

The journal is **synthesized from a structured event log rather than free-form generated**, **selects a single dominant event** per day by a fixed priority order, and is **rendered in the tenure-derived voice phase**. It additionally synthesizes ambient/milestone/return-after-absence entries on days with no operational events, so the narrative remains continuous.

### 6.3 Detailed operation

1. For a given day, gather that day's trust events. Classify into mistake, demotion, promotion, team change, recommendation-resolved, recommendation-made, and aggregated operational wins/setbacks.
2. Select the single **dominant** category by a fixed priority order (e.g., a flagged mistake outranks a demotion, which outranks a promotion, etc.).
3. Render the dominant event into prose using phase-specific templates and a phase-appropriate closing "verdict" (e.g., "Fair. Rebuilding." vs. "Pattern holding.").
4. On days with no qualifying events, synthesize an ambient anchor (deterministically selected from a per-phase pool by day-modulo-pool-length), a milestone entry when a phase boundary is crossed, or a re-emergence entry sized to the length of an absence.
5. Each entry carries a stable id, the relationship day, the source event ids (for traceability), the phase, and a word count.

### 6.4 Claimable points

- Generating at most one reflective journal entry per day by deterministic selection of a single dominant event from a structured event log.
- Maintaining narrative continuity on event-less days via deterministic ambient, milestone (phase-boundary), and absence-aware re-emergence synthesis.

---

## 7. Mechanism D — Deterministic Briefing Ranker and Validated Letter

### 7.1 What it is

A method for producing a daily briefing that (a) scores each candidate staged action by a weighted sum of urgency, importance, confidence, and freshness; (b) selects at most a small fixed number (e.g., three) of the highest-scoring actions; and (c) composes them into a single briefing "letter" that is validated against style ("voice") rules and structural ("shape") rules before release, falling back to a canonical "quiet" template when no action qualifies.

### 7.2 Why it is novel

The selection is **deterministic and stable** (ties broken by recency then id, so repeated renders are identical), the score combines **computed urgency and importance** (each derived from category tier, payload signals such as monetary amount or VIP status, keyword indicators, and an anti-starvation aging term), and the composed output is **gated by automated voice and shape validators** that reject non-conforming output rather than emit it. The briefing is a **snapshot** — never stored or edited — while an underlying action ledger remains the source of truth.

### 7.3 Detailed operation

1. **Urgency** is computed from a category/kind base, overridden by explicit payload urgency, nudged by urgency/question keywords, and reduced by an aging penalty so old items do not dominate indefinitely.
2. **Importance** is computed from category tier and modified by financial value bands, customer-status tags (e.g., VIP, returning), and safety/agency keywords.
3. **Score** = 0.35·urgency + 0.35·importance + 0.20·confidence + 0.10·freshness, where freshness decays linearly to zero over a fixed window.
4. The top-N (default 3) are selected deterministically.
5. The letter composer renders each action block with timestamp, voice-safe prose (long passthrough text is split to satisfy sentence-length caps; emoji stripped), an optional single memory citation, and a confidence line; it then runs shape validation (caps action lines, enforces a sign-off) and voice validation (rejects emoji, hedging, sycophancy) before returning.

### 7.4 Claimable points

- Deterministic, stable selection of a capped set of agent actions for human review by a specific weighted scoring of computed urgency, computed importance, confidence, and decaying freshness, including an anti-starvation aging term.
- Releasing the composed briefing only after passing automated style- and structure-validators, with a canonical fallback when no action qualifies.

---

## 8. Mechanism E — Voice-Validated Agent Memory ("Notebook")

### 8.1 What it is

A persistent agent memory of short entries, bucketed and subject-tagged, with **asymmetric validation**: when the agent itself authors or rewrites an entry, the text must pass style ("voice") validation or the write is rejected; when a human edits an entry, validation is bypassed because the human may write anything. Entries are retrieved by a relevance function (exact-subject, then tag, then token overlap) that supplies citations to the briefing.

### 8.2 Why it is novel

The **asymmetry** — machine-authored memory is held to a style contract, human-authored memory is not — is the core novel point, ensuring the agent's own remembered "voice" stays consistent while preserving full user freedom. Retrieval results feed the briefing's citation slots, tying memory to action justification.

### 8.3 Claimable points

- An agent memory store applying generative-style validation to machine-authored writes while exempting human edits from that validation.
- Coupling relevance-ranked memory retrieval to the justification/citation slots of an agent briefing.

---

## 9. Mechanism F — Edit-Synchronized Semantic Re-Indexing of Notes

### 9.1 What it is

A method for keeping a vector/semantic search index consistent with editable meeting notes. When a note is created or **edited**, the system (a) flattens the structured note (title, date, attendees, summary, key points, action items, decisions, next steps, transcript excerpt) into a dense text block, (b) chunks it with overlap on sentence/paragraph boundaries, (c) **deletes all prior embedding chunks for that note**, (d) re-embeds the new chunks, and (e) stores them — all as a **non-blocking background task** so the edit response is not delayed. Semantic search then ranks chunks by cosine similarity and deduplicates to one best chunk per note.

### 9.2 Why it is novel

The **delete-then-re-embed-on-edit** cycle keeps the semantic index strictly consistent with user edits to rich-text notes (a known failure mode where edited text drifts from its original embeddings), executed asynchronously so it never blocks the user, and scoped per-user/per-note for multi-tenant isolation.

### 9.3 Claimable points

- Maintaining semantic-search consistency for editable notes by, on each edit, deleting prior embedding chunks for that note and re-embedding the edited content as a background task.
- Per-note deduplication of semantic-search results to the single highest-scoring chunk.

---

## 10. Drawings to Attach (informal sketches are acceptable)

1. **FIG. 1** — System architecture: user, chief agent, sub-agents, event store, briefing, journal, notebook, notes knowledge base.
2. **FIG. 2** — Trust-ladder state machine: ranks, promotion/demotion/probation transitions, the recommendation→approval delegation chain.
3. **FIG. 3** — Event-log replay → Standing map (data-flow diagram).
4. **FIG. 4** — Persona phase timeline vs. relationship days.
5. **FIG. 5** — Journal synthesis flow: day events → dominant-event selection → phase-voiced entry.
6. **FIG. 6** — Briefing pipeline: candidate actions → scoring → top-N selection → voice/shape validation → letter.
7. **FIG. 7** — Note edit → flatten → chunk → delete old vectors → re-embed → store (background task).

## 11. Items to Expand Before Filing (placeholders)

> The following two features appear in the product's commit history and may add novelty, but the implementation was **not** fully analyzed when this draft was prepared. Describe each with the same level of step-by-step detail as §4–§9 before filing, or omit them.

- **Background recording persistence + floating overlay control (notetaker):** how recording state survives across navigation/contexts (e.g., persisted in a service worker / global store), and the always-available floating overlay control. **[DESCRIBE THE MECHANISM]**
- **Speaker/Room mode for participant recording:** how multi-participant audio is captured and attributed. **[DESCRIBE THE MECHANISM]**
- **Autonomous multi-channel AI background agents + trigger pipeline:** how triggers are detected, queued, dispatched, and deduplicated across channels. **[DESCRIBE THE MECHANISM]**

## 12. Inventor & Filing Checklist

- [ ] Replace all `[BRACKETED]` placeholders, especially inventor legal name(s).
- [ ] Expand §11 items or delete them.
- [ ] Create FIG. 1–7 (hand-drawn or simple diagrams are fine for a provisional).
- [ ] Determine entity status (most solo founders qualify as **micro entity**).
- [ ] Complete USPTO cover sheet **form SB/16** (provisional).
- [ ] File at **patentcenter.uspto.gov**; pay the provisional fee (~$65 micro / ~$130 small).
- [ ] **Calendar the 12-month deadline** to file the non-provisional — the provisional expires and gives nothing if missed.
- [ ] File **before** any public launch / Web Store listing if non-US protection matters.

---

*This document is an engineering disclosure prepared to support a provisional patent filing. It is not legal advice. Have a registered patent attorney or agent review claim scope before filing the non-provisional application.*
