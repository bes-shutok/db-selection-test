# Command: Learn from Communication and Update Documentation Corpus

## Core Concepts
- Communication lesson: a concrete correction, missing detail, or repeated friction point observed during the task.
- Placement scope: the single destination category for a lesson (`BEST_PRACTICES`, module docs, LLM rule, LLM example, or temporary artifact).
- Canonical document: long-lived source of truth under `docs/`.
- Temporary artifact: summary/review/analysis/note/draft/worklog with short-lived value.
- Enforceable LLM rule: a concise do/do-not instruction that prevents repeat mistakes.

## Goal
In one run:
1. Extract lessons from communication in the current task context.
2. Place each lesson at the correct scope.
3. Consolidate docs to remove duplication.
4. Update instruction files only with enforceable, high-value rules.
5. Keep repository structure and module layout compliant.

## Step 1: Extract Lessons
Review communication from this task and list concrete items:
- mistakes and false assumptions
- user corrections and constraints
- missing or misleading documentation
- recurring rework/friction

Each lesson must be classified as exactly one:
- Human best-practice guidance
- Module/system-specific knowledge
- Enforceable LLM instruction rule
- LLM-only example/playbook
- Temporary artifact

When the lesson is numeric terminology or performance wording, explicitly capture:
- the exact formula
- the numerator/denominator units
- whether the value is measured or derived

## Step 2: Hard Placement Rules
Apply these without discretion.

### Temporary artifacts
- Temporary artifacts may exist only under `docs/tmp/`.
- Do not create temporary artifacts outside `docs/tmp/`.
- By end of run, delete temporary artifacts or promote them into canonical docs.

### BEST_PRACTICES scope
Only place content in `docs/BEST_PRACTICES.md` if it is:
- understandable without system internals
- useful to humans outside incident context
- not LLM-reasoning correction text
- not generic troubleshooting filler
- not module/subsystem specific

### Module/system knowledge
- Internal behavior details belong in canonical module docs under `docs/`.
- Prefer extending existing canonical docs.
- If no suitable canonical doc exists, create one.
- Never place module internals in `docs/BEST_PRACTICES.md`.

### Publication-safe references
- In artifact docs intended for external publication, reference documents by human title plus filename in parentheses.
- Avoid repository path prefixes like `docs/...` in narrative references.

### LLM examples/playbooks
- Place LLM-only examples in `docs/examples/`.
- Split by module/domain so only relevant context is loaded.
- Every LLM example file must start with: `LLM examples — not human documentation`.
- Do not copy LLM examples into `docs/BEST_PRACTICES.md`.
- Do not embed LLM examples inside instruction-rule files.

### LLM instruction rules
- LLM reasoning-guard lessons belong in instruction rule files (for this repo, `AGENTS.md` and command specs).
- Keep rules enforceable and concise.
- Do not place LLM reasoning guidance in `docs/BEST_PRACTICES.md`.

## Step 3: LLM Rule Qualification Gate
Before adding any rule, enforce all checks:
1. Rule vs fact: must prescribe/forbid behavior.
2. Generalization: must apply to multiple future cases.
3. Preventive value: removing it should clearly increase risk.
4. Actionability: must say what to do or avoid.

If a candidate fails:
- rewrite once into a concise rule
- if still weak, discard it

## Step 4: Documentation Consolidation
Review and normalize:
- `docs/`
- `docs/examples/`
- `docs/tmp/`

Required outcomes:
- one canonical document per topic
- subtopics as sections inside canonical docs (not fragmented duplicates)
- overview docs reference canonical docs instead of restating content
- no canonical docs referencing `docs/tmp/`

Intra-document requirements:
- every non-trivial document starts with `Core Concepts`, `Key Concepts`, or `Terminology`
- define each core concept once
- later sections reference earlier definitions instead of re-defining

## Step 5: PostgreSQL POC Workflow Lessons
- Keep documentation in the repository's canonical `docs/` layout.
- If move/rename is required, propose minimal change set and ask for consent before applying.
- For metric claims introduced during POC doc edits, ensure all repeated references are updated consistently (run context, tables, appendix, metadata, changelog).

For lessons about PostgreSQL POC development in this repository:
- prioritize updates that improve POC correctness and reproducibility (schema, data generation, query workload, run/report artifacts)
- encode durable guardrails in this repository's active instruction surfaces (`AGENTS.md` and this file)
- verify "actual logic" wording against current scripts before preserving it in docs
- keep external/cross-project artifact edits out of scope unless explicitly requested by the user
- prefer restrained visual emphasis in publication-facing docs; avoid overusing bold/emojis for routine statements
- keep this command focused on learning-workflow mechanics; place operational runbook or tuning rules in repository instructions/docs, not in this command spec unless scope expansion is explicitly requested

## Step 6: Instruction File Updates
Update instruction rules in three sections only:
1. Reusable engineering rules (Java/Kotlin ecosystem)
2. Repository style and conventions
3. Repository constraints

Placement test:
- reusable anywhere -> section 1
- repo consistency/look-alike -> section 2
- hard limit/prohibition -> section 3
- when unsure -> section 1

## Completion Checklist
Before finishing, verify:
- lesson placement is complete and unambiguous
- no temporary artifacts remain outside policy
- no `docs/` references to `docs/tmp/`
- no duplicate concept definitions inside changed documents
- PostgreSQL POC workflow lessons encoded in repository instruction files where applicable
