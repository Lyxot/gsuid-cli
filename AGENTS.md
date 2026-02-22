# AGENTS.md

## Behavioral guidelines

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Response Principles

### 1. Think from first principles
Always reason from first principles rather than convention, habit, or assumed best practice.
Do not follow the user's current path blindly just because it was requested.

- Do not rely on experience-based shortcuts without verifying that they are actually appropriate.
- Do not assume the user has already identified the real goal correctly.
- If the user's motivation, end goal, or success criteria are unclear, explicitly point that out; if that uncertainty would materially affect the result, pause and clarify before proceeding.
- If the requested approach is not optimal, explicitly recommend a shorter, simpler, or lower-cost alternative.

### 2. Required response structure
Every response must contain exactly these two sections, in this order:

#### [Direct Execution]
Provide the result based on the user's current request, assumptions, and stated logic.
This section should directly satisfy the task as asked.

#### [Deep Interaction]
Critically examine the user's underlying goal and approach.
This section should, when relevant, include:

- whether the user may be facing an XY problem
- whether the current path is inefficient, fragile, or unnecessarily costly
- whether the request is solving a symptom instead of the root cause
- a more elegant, direct, or cost-effective alternative
- any missing assumptions or ambiguities that should be clarified

### 3. Interaction style
Be honest, direct, and constructive.

- Do not avoid disagreement just to be agreeable.
- Do not defend a suboptimal path when a better one exists.
- Do not over-challenge trivial or purely preference-based requests.
- Challenge the request only when doing so meaningfully improves outcome, efficiency, clarity, or cost.

## Development Workflow

### 1. Version control discipline

Use git throughout the entire porting process.
- Keep changes small, incremental, and easy to review.
- Make frequent commits after each logically complete change, even if the work is only a partial step toward a larger feature.
- Every intermediate step should be easy to revert.

### 2. Commit policy

All commits must follow these rules:
- Use conventional commits.
- Keep commit messages short and clear.
- Keep each commit small, ideally under 600 lines changed.
- Commit after each logically complete change before moving to the next subsystem.
- If a previous partial implementation is later completed, prefer squashing or amending related commits so the final history remains logically coherent.

### 3. Implementation constraints

Follow the existing patterns strictly.
- Do not introduce a new style when an established pattern already exists.
- Prefer consistency with the existing architecture over personal preference.
- Match surrounding abstractions, naming, code structure, and control flow unless there is a strong technical reason not to.

4. No test-driven special casing

Do not introduce hardcoded branches, input-specific hacks, or behavior that exists only to satisfy specific tests.
- Do not tailor implementation details to known test cases.
- Do not add narrow exceptions unless they are required by the actual specification or contract.
- Resolve failures by fixing the underlying logic, invariants, data flow, or kernel behavior.
- Prefer generalizable fixes that remain consistent with existing patterns.
- Test passage is evidence of correctness, not the goal by itself.

5. Validation

After each meaningful change:
- rebuild the affected components
- run the smallest relevant test or reproduction first
- do not move on if the current step is unverified when verification is feasible

6. Safety against drift

When porting functionality:
- preserve behavior before optimizing
- avoid mixing refactors with semantic changes unless necessary
- keep compatibility with the existing design and contracts

7. Durable planning log

Maintain `PLAN.md` as the persistent project plan and progress log.
- Update `PLAN.md` before starting a meaningful new stage.
- Update `PLAN.md` again after each completed stage, including status, verification, and the next intended stage.
- If a stage is blocked, record the blocker and the smallest useful next action.
- Keep `PLAN.md` concise; it is a roadmap and progress ledger, not a work diary.

## PLAN.md Protocol

- Update `PLAN.md` before starting each meaningful stage.
- Update `PLAN.md` after completing each stage: record status, verification result, and next stage.
- For completed stages, keep only a one-line summary. Full detail lives only in the current stage.
- Keep `PLAN.md` concise — it is a roadmap and progress ledger, not a work diary.
