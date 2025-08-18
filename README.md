# Release Notes Builder (Python CLI)

Generates crisp release notes across multiple repos using GitHub data + LLM consolidation.

## Features

- Fetch merged PRs per repo between tags/SHAs (auto-detect previous tag if missing) or by date.
- Deterministic pre-classification (Features, Fixes, Chore).
- LLM consolidation (OpenAI) into structured JSON (validated) and Markdown rendering.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables in .env file:

```
GITHUB_TOKEN=...
OPENAI_API_KEY=...
```

## Quick start

```bash
python -m release_notes_builder.cli --config sample_config.yaml
```

Debug mode:

```bash
python -m release_notes_builder.cli \
  --config sample_config.yaml \
  --log-level DEBUG
```

## Notes

- If `--since-ref` is omitted, the tool attempts to use the previous tag on the repo.
- If refs cannot be compared, you can provide `--since-date YYYY-MM-DD`.
- Output file: `RELEASE_NOTES.md`.

## Limitations & future improvements

- Date window is derived by compare API and used to search merged PRs; edge cases may include cherry-picks.
- Consider switching to GraphQL for richer PR queries and better pagination.
- Optional publishers: GitHub Releases, Notion, Slack.
