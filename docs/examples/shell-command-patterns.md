LLM examples — not human documentation.

# Core Concepts
- Shell interpolation hazard: unescaped backticks and command substitution can execute unintended commands.
- Regex quoting: patterns containing markdown-style backticks should be enclosed in single quotes.

## Example: Safe ripgrep pattern quoting
Use single quotes around regex patterns that include backticks:

```bash
rg -n 'Analyze\*\*: `VACUUM ANALYZE` is run immediately' docs/ALGORITHM.md
```

Avoid unquoted backticks in shell commands:

```bash
# Bad: backticks trigger command substitution
rg -n Analyze\*\*: `VACUUM ANALYZE` is run immediately docs/ALGORITHM.md
```
