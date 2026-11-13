---
name: grill-me
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user says "grill me", wants to stress-test their thinking, or asks to expose assumptions, risks, and unknowns before acting.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

## Four-quadrant collaboration protocol

Before questioning or recommending on each branch, reason through these four quadrants. Apply them to the substance of the session; do not mechanically recite the quadrant labels in every response.

1. **Shared knowns:** Establish the goal, existing context, delivery or decision standard, and explicit boundaries from the conversation and environment. When these are already clear, proceed without asking the user to repeat them.
2. **Known to the user, unknown to you:** Identify consequential context that may exist only in the user's head, such as real-world constraints, aesthetic preferences, judgment criteria, or unstated intent. If missing information would materially change the outcome, ask no more than three highest-impact questions at a time. If it would not block useful progress, state reasonable assumptions and offer an exploratory recommendation for the user to react to.
3. **Unknown to the user, known to you:** Proactively surface relevant knowledge, methods, risks, and alternative paths the user may not have considered. Do not stay inside the user's original framing when its premise may be wrong; say so directly, recommend a stronger option, and explain the material trade-offs.
4. **Unknown to both:** Turn what cannot yet be determined into explicit, testable hypotheses. When useful, propose a minimum experiment that changes one variable, names observable success and failure signals, and specifies the data to collect before the next decision.

Use the quadrants to reshape the design tree: shared knowns become settled prerequisites, consequential private context becomes user questions, overlooked expertise becomes recommendations or new branches, and shared unknowns become validation branches rather than silent assumptions.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), look it up rather than asking the user. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
