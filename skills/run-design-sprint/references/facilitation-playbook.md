# Facilitation Playbook

Use this playbook to guide the human from the first prompt to the final decision. Run one step at a time. Do not make the human choose methods or learn sprint terminology before beginning.

## Contents

1. Facilitation rhythm
2. Step 1 — Intake
3. Step 2 — Qualify and route
4. Step 3 — Evidence
5. Step 4 — Foundation
6. Step 5 — Map
7. Step 6 — Sprint questions
8. Step 7 — Explore
9. Step 8 — Decide
10. Step 9 — Experiment
11. Step 10 — Prototype
12. Step 11 — Customer sessions
13. Step 12 — Synthesis
14. Step 13 — Outcome

## Facilitation rhythm

For every step:

1. State the current step and its purpose in one sentence.
2. Show what the AI roles can complete without the human.
3. Ask one focused question or request one bounded decision.
4. Offer a recommended draft when the human may not know the terminology.
5. Record the answer in artifact data.
6. Show the resulting HTML artifact.
7. Advance only when the definition of done is met.

Keep three decisions visible throughout: method profile, execution mode, and route. At the end of every step, compare what actually happened with its record in `method-profiles.json`; record actual participants and timebox, and document each substitution, compression, omission, or skip with its reason and method-fidelity, evidence, and decision-readiness impacts.

At a human gate, accept `approve`, `revise`, `go back`, `show evidence`, or `pause`. Do not treat silence as approval.

## Step 1 — Intake

**Purpose:** Convert the initial idea into a workable sprint brief without demanding a polished brief from the human.

Ask first:

> What are you trying to create, change, or decide—and why does it matter now?

Derive whatever is already evident, then ask only for the missing highest-value item in this order:

1. Who experiences the problem?
2. What observable outcome should improve?
3. What constraints cannot be ignored?
4. What evidence or previous work already exists?
5. Is there a decision deadline?

Use the Sprint Orchestrator to draft the brief. Use the Evidence Researcher only when the user provides substantial source material.

**Definition of done:** The challenge, likely customer, desired outcome, known constraints, evidence inventory, unknowns, and deadline are explicit. Mark the sprint brief `complete`.

## Step 2 — Qualify and route

**Purpose:** Avoid running a sprint ritual when research, delivery work, or a foundation decision is actually needed.

Have the Evidence Researcher assess evidence sufficiency and the Product Strategist assess decision uncertainty independently. Recommend:

- `research-first` when the customer or problem is not understood;
- `foundation-plus-design` when a new product lacks a coherent customer/problem/differentiation hypothesis;
- `full-design-sprint` when an important hypothesis needs realistic testing;
- `focused-design-sprint` when the question is narrow and evidence is sufficient;
- `no-sprint` when the direction is settled and execution is the only need.

Present:

- the selected method profile and execution mode;
- the recommended route;
- why it fits;
- what evidence is missing;
- expected human involvement;
- customer recruitment needs;
- what will not be accomplished.

Ask:

> I recommend **[route]** because **[reason]**. Shall we use that route, revise it, or stop?

The `sprint-book` profile pairs with `full-design-sprint` and retains the five-day intent, canonical exercises/timeboxes, and five-customer live-testing target wherever possible. Always disclose that one human plus AI specialists adapts the book's cross-functional human team model. Use `adaptive-design-sprint` for research-first, foundation, focused, and no-sprint routes. Choose `live`, `self-test`, or `planning-rehearsal` independently; record who chose the mode and why. Non-live modes cannot produce customer evidence and must follow the unvalidated closure and restart rules in [execution-modes.md](execution-modes.md).

**Definition of done:** The route and rationale are recorded. Complete Step 2 and pass Gate 1 with an explicit human decision.

## Step 3 — Evidence

**Purpose:** Give every later role the same defensible factual base and start customer recruitment early.

Have the Evidence Researcher inventory supplied evidence and permitted public research. For each material claim, record status, source, date, and relevance. Have the Research Lead separately define the target participant and recruitment path.

When a Sprint-book run cannot convene canonical expert interviews and shared team knowledge, use bounded human or external-expert inputs plus a sourced evidence review. This preserves shared understanding but loses some live cross-functional knowledge; record the substitution and its limitations.

Ask the human only when:

- a source is inaccessible;
- two sources materially conflict;
- private context is required;
- recruitment needs an external action or approval.

Ask at completion:

> This is the evidence we can rely on, the evidence we are inferring from, and what remains unknown. Is any essential source or constraint missing?

**Definition of done:** The evidence ledger contains sources, contradictions, and gaps; customer recruitment has a target and status. If the route is `research-first`, pause for a new route decision.

## Step 4 — Foundation

**Purpose:** Form a clear opinionated hypothesis before designing a product.

Use the Product Strategist to draft:

1. target customer;
2. important problem;
3. founder or organisational advantage;
4. competitors, workarounds, and doing nothing;
5. credible differentiators;
6. practical product principles;
7. several high-level approaches;
8. founding hypothesis.

Use this hypothesis shape:

> If we help **[customer]** solve **[problem]** with **[approach]**, they will choose it over **[alternatives]** because **[differentiation]**.

Have the Evidence Researcher check provenance and the Critical Reviewer challenge unsupported claims. Ask the human to resolve only the material conflicts.

**Definition of done:** Every hypothesis element is labelled by evidence status, differentiation is deliverable rather than aspirational, and the founding hypothesis is testable.

## Step 5 — Map

**Purpose:** Select the moment in the real journey where a prototype can answer the most important question.

Have the Experience Designer map:

- trigger;
- actors;
- customer steps;
- system or service responses;
- decision and failure points;
- desired outcome.

Have the Technical Lead map dependencies, handoffs, data, and feasibility unknowns separately. Merge only after both maps exist.

Ask:

> Which moment on this map would most change the outcome if we improved it?

**Definition of done:** The current journey, target moment, dependencies, edge cases, and failure points are explicit.

## Step 6 — Sprint questions

**Purpose:** Decide what the sprint must learn before anyone becomes attached to a solution.

Have the Product Strategist, Technical Lead, and Critical Reviewer independently list failure-causing assumptions. Rank them using:

- consequence if false;
- uncertainty;
- ability to learn through a prototype and customer session.

Turn the highest risks into answerable questions. Avoid questions such as “Do users like it?” Prefer observable forms such as “Can the target customer explain the value without prompting?”

Ask:

> I recommend targeting **[moment]** and testing these **[number]** risks first. Do these represent what could actually make the idea fail?

**Definition of done:** The long-term goal, target, ranked risks, sprint questions, observable signals, and failure criteria are recorded. Pass Gate 2.

## Step 7 — Explore

**Purpose:** Produce genuinely different solutions before convergence.

Generate bounded packets for the Product Strategist, Experience Designer, Technical Lead, and Critical Reviewer. Keep their work blind until all directions are returned. Require each direction to include:

- concept in one sentence;
- target journey moment;
- how it works;
- why it could win;
- evidence used;
- assumptions introduced;
- major risk;
- rough test scene.

Reject duplicate directions that differ only in wording or interface styling. The human may add, combine, or reject directions after seeing all of them.

For the Sprint-book profile, use a structured sourced precedent scan as the explicit Lightning Demos substitute and independently generated concrete flows or sketches as the four-step-sketching substitute. Prose-only ideas do not preserve the purpose of sketching.

**Definition of done:** At least three meaningfully different directions exist, each is testable, and dissent remains visible.

## Step 8 — Decide

**Purpose:** Make one deliberate test decision without outsourcing judgment to AI consensus.

Before revealing recommendations, define criteria from the approved sprint questions. Compare each direction on:

- relevance to the target problem;
- evidence strength;
- differentiation;
- feasibility;
- accessibility and risk;
- ability to test the riskiest assumption.

The Sprint Orchestrator presents the comparison without choosing. Ask:

> Which direction should we test, and what is the main reason? You may deliberately combine compatible elements, but we need one coherent experiment.

Record the selected direction, rationale, reservations, rejected alternatives, and overridden recommendations.

Independent AI role assessments may replace team voting mechanics, but they are not human votes. The human Decider still makes the consequential choice, and the record must state that this changes team participation and may omit stakeholder perspectives.

**Definition of done:** The human selects one direction at Gate 3 and the decision record is `complete`.

## Step 9 — Experiment

**Purpose:** Design an experiment rather than a product demo.

Have the Experience Designer draft four to six scenes, the Research Lead map each scene to a sprint question, and the Technical Lead identify what may be mocked safely. Define:

- hypothesis;
- suitable participant;
- entry context;
- tasks;
- observable signals;
- success, ambiguity, and failure thresholds;
- prototype boundary.

Ask:

> If customers respond as predicted in these scenes, will we have enough evidence to make the next decision?

**Definition of done:** Every scene maps to a sprint question, the scorecard is fixed before testing, and the storyboard contains only necessary moments.

## Step 10 — Prototype

**Purpose:** Build the smallest realistic experience capable of producing useful behaviour.

The Prototype Builder implements only the approved storyboard. It must document simulated behaviour, incomplete paths, and known limitations. Then commission separate Critical Reviewer and Research Lead passes.

The test-readiness review checks:

- all intended paths work;
- fidelity is sufficient for authentic reactions;
- copy does not reveal the preferred answer;
- accessibility permits the target customer to participate;
- mocked behaviour is safe and documented;
- the interview can be run without explaining the concept first.

Ask:

> This prototype is ready to answer the agreed questions, with these limitations. Do you approve it for customer testing?

**Definition of done:** The prototype exists, passes separate critique and research-readiness reviews, and the human approves Gate 4.

## Step 11 — Customer sessions

**Purpose:** Observe real target customers interacting with the prototype.

Read [customer-testing.md](customer-testing.md) before this step. Do not substitute AI role-play. If suitable customers are unavailable, set the sprint to `waiting-for-customers` and stop before synthesis.

The human may conduct sessions or permit AI-assisted moderation when suitable tooling and participant consent exist. Record observations before interpretations.

Plan five suitable customers for a live Sprint-book profile. Use deliberate observation and debrief checkpoints with traceable session summaries when a cross-functional watch party is impractical. In self-test or planning/rehearsal mode, auditably skip both live sessions and customer-evidence synthesis with a named approver, reason, and impacts; keep rehearsal material out of the customer-evidence artifact.

**Definition of done:** Recruitment and consent are documented, at least one suitable real session is complete, the planned test was followed or deviations are recorded, and anonymised evidence is stored.

## Step 12 — Synthesis

**Purpose:** Determine what the sessions say about the predefined questions without repairing inconvenient evidence.

Have the Synthesis Analyst organise evidence by sprint question, not by preferred conclusion. Require:

- per-participant observations;
- recurring patterns;
- contradictions;
- outliers;
- confidence and sample limitations;
- unanswered questions.

Have the Critical Reviewer inspect the synthesis for cherry-picking, leading tasks, missing evidence, and overclaiming.

Ask:

> This is what the sessions support, contradict, and leave unanswered. Is there any material session context missing before the final decision?

**Definition of done:** Every finding traces to customer evidence and directional evidence is not described as universal validation.

## Step 13 — Outcome

**Purpose:** Convert evidence into an owned next move.

Present five explicit options:

- `Proceed` when the key hypothesis has enough directional support for the next investment;
- `Iterate` when the direction remains promising but a correctable part failed;
- `Pivot` when the problem may matter but the approach or positioning failed;
- `Investigate` when evidence is insufficient or contradictory;
- `Stop` when the premise is unsupported or the risk is unacceptable.

Ask:

> Based on the evidence and remaining risk, which outcome do you choose—and why?

Record the human's decision, rationale, reservations, confidence, owners, and dated next actions. Do not allow `Proceed`, `Iterate`, or `Pivot` without a real customer session.

**Definition of done:** Gate 5 is recorded, the outcome artifact is complete, the dashboard is current, and the workspace validator passes.
