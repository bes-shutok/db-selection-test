# Best Practices

## Core Concepts
- Publishable artifact document: documentation intended to be consumed outside the repository UI (for example, in Confluence).
- Canonical reference style: human-readable document title followed by filename in parentheses.
- Source-of-truth check: verifying documentation claims against the script or code path that actually executes.

## Documentation Communication Practices
- Publishable docs are clearer when cross-document references use titles (for example, "Testing Algorithm and SQL Reference (`ALGORITHM.md`)") instead of repository path links.
- Reader trust improves when "actual logic" snippets are revalidated against current implementation before publication.
- Handoff docs are easier to maintain when they separate durable guidance from run-specific observations.
- Quantitative statements are easier to verify when they include units and a visible formula (for example, total operations vs per-row average).
- Data refresh edits are safer when run IDs, metric tables, appendix snapshots, and metadata are updated in one consistency pass.
