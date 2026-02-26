LLM examples — not human documentation.

# Core Concepts
- RFC artifact output: generated or edited content derived from a design-RFC command workflow.
- Publication-safe reference: document title plus filename in parentheses, without repository path prefixes.

## Example: Publication-safe document references
Prefer:
- Testing Algorithm and SQL Reference (`ALGORITHM.md`)
- Run Modes (`RUN_MODES.md`)

Avoid:
- `docs/ALGORITHM.md`
- `docs/scripts/RUN_MODES.md`

## Example: Validate "Actual Logic" snippets
Before keeping a code block labeled "Actual Logic from ...":
1. read the current script implementation
2. check iteration model, output filenames, and phase handling
3. update snippet text if behavior changed

## Example: Scope placement from RFC feedback
- Human-readable publication wording -> `docs/BEST_PRACTICES.md`
- Repository-specific documentation guardrails -> `AGENTS.md`
- Command workflow guardrails -> `.opencode/command/learn.md`
