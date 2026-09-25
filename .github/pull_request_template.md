## Feature Report

### What Changed

-

### Why This Exists

-

### User / Operator Impact

-

### How It Works

-

### Files And Contracts Touched

-

### Affected Surfaces

- [ ] Hermes chat or wrapper
- [ ] Codex
- [ ] Claude Code
- [ ] Hermes runtime or handoff
- [ ] Generic executor
- [ ] Not executor-specific

## Validation

Check only commands that completed successfully. Leave non-applicable checks
unchecked and explain why under **Not Tested / Not Applicable**.

- [ ] `uv run --group lint ruff check src tests`
- [ ] `PYTHONPATH=tests uv run python -m unittest discover -s tests -v`
- [ ] `uv run python -m compileall -q src tests`
- [ ] `uv run python -m omh.cli docs workflows --check`
- [ ] `uv run python -m omh.cli docs roles --check`
- [ ] `uv run python -m omh.cli docs capability-families --check`
- [ ] `uv run python -m omh.cli docs skill-shortlist --check`
- [ ] `uv run python -m omh.cli harness validate`
- [ ] `uv run python -m omh.cli release checklist --json`
- [ ] `uv run python -m omh.cli release hermes-smoke`
- [ ] `git diff --check`
- [ ] `omh --help`
- [ ] `omh --omh-home /tmp/omh-smoke --hermes-home /tmp/hermes-smoke release hermes-smoke --install-path setup --omh-command omh --include-command-smoke`
- [ ] Relevant workflow-learning review queue smoke, when learning contracts changed:
- [ ] Relevant dry-run or smoke command:
- [ ] Manual Hermes/TUI check, or explicit reason it was not run:

### Observed Evidence

- Targeted tests, commands, CI checks, and manual behavior actually observed:
-

### Not Tested / Not Applicable

- Skipped checks and the concrete reason each one does not apply:
-

## Risk

-

## Compatibility / Rollout

-

## Release / Claims

- [ ] Release-channel impact considered (`stable`, `preview`, or `local`)
- [ ] Runtime/native capability claims are backed by evidence or marked as not observed
- [ ] Prepared handoffs or plans are labeled `prepared_not_observed`, never as execution, review, CI, or merge evidence
- [ ] Evidence contains no credentials, raw prompts, raw platform events, transcripts, or unrelated private data
- [ ] Known manual Hermes checks are listed, including any `omh release hermes-smoke --live` gap

## Follow-Up

-
