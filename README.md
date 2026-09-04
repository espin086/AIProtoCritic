# AIProtoCritic

A GitHub Actions bot that reviews Protocol Buffer (`.proto`) changes in a pull request and posts the review back as a PR comment. It runs a local Llama 3.1 model through Ollama inside the CI job, feeds it the text of an API design guide PDF checked into the repo, and asks it to grade the diff against that guide only. Output is a single comment with three sections: issues (❌), suggestions (🟡), and good practices (✅), each tied to a line number and a quoted guideline.

The point is that the review rules live in a document you control (`.github/api_design_guide.pdf`), not in the model's general opinions. No external LLM API is called and no API key is needed; the model runs on the GitHub runner.

## Features

- Triggers on pull requests (`opened` and `synchronize`).
- Pulls the PR's changed file list from the GitHub API and keeps only `.proto` files. Exits quietly if there are none.
- Reads `.github/api_design_guide.pdf` with PyPDF2 and passes the extracted text to the model as the sole review standard. If the PDF is missing or unreadable, it falls back to a generic "follow standard Protocol Buffer API design best practices" instruction and keeps going.
- Diffs each changed `.proto` against `origin/main` and reviews one file at a time.
- Posts a single combined comment on the PR issue thread.

## Requirements

- A GitHub repository with Actions enabled. The workflow requests `pull-requests: write` so the bot can comment; the built-in `GITHUB_TOKEN` covers it.
- Python 3.9 (set by the workflow).
- `PyPDF2` and `requests` (installed by the workflow step).
- Ollama with the `llama3.1` model, provisioned in CI by `pydantic/ollama-action@v3`. The script talks to it at `http://localhost:11434/api/chat`.
- An API design guide PDF at `.github/api_design_guide.pdf`.

There is no `requirements.txt` or `pyproject.toml`; dependencies are declared inline in the workflow.

## Installation

Copy the two files into the repo whose protos you want reviewed:

```
.github/workflows/proto_review.yaml
.github/ai_review_bot.py
```

Then add your own `.github/api_design_guide.pdf`. Nothing else to configure. There are no repository secrets to set.

## Usage

Normal use is automatic: open a PR that touches a `.proto` file and the bot comments on it.

To run the script by hand, it needs the same three environment variables GitHub Actions provides, plus a reachable Ollama server:

```bash
ollama serve &
ollama pull llama3.1

pip install PyPDF2 requests

export GITHUB_TOKEN=ghp_...                 # needs pull-requests write
export GITHUB_REPOSITORY=espin086/AIProtoCritic
export GITHUB_EVENT_PATH=/path/to/event.json   # JSON with a top-level "number" (the PR number)

python .github/ai_review_bot.py
```

The script reads the PR number from `event_data["number"]` in the event payload, and it shells out to `git diff origin/main <file>`, so the clone needs full history. The workflow uses `fetch-depth: 0` for that reason.

Environment variables used:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Auth for reading PR files and posting the comment |
| `GITHUB_REPOSITORY` | `owner/repo` used to build API URLs |
| `GITHUB_EVENT_PATH` | Path to the event JSON the PR number is read from |

The model name (`llama3.1`), the Ollama endpoint, and the guide path are hardcoded in the script.

## Project structure

```
.github/
  ai_review_bot.py        The whole bot: fetch changed protos, read the guide, call Ollama, post the comment
  api_design_guide.pdf    The review standard the model is told to grade against
  workflows/
    proto_review.yaml     PR-triggered job: checkout, Python 3.9, Ollama + llama3.1, deps, run the script
supertest.proto           Sample proto used to exercise the bot on a PR
LICENSE                   MIT
.gitignore                Standard Python ignores
```

`supertest.proto` defines a small `UserManagementService` with deliberately off-convention names (`FetchUserDetails`, `RemoveUserAccount`, camelCase fields, an empty `VoidResult`), which is useful as a test case for the reviewer.

## How it works

1. The workflow fires on a PR, checks out with full history, installs Python and deps, and starts Ollama with `llama3.1`.
2. `ai_review_bot.py` reads the event JSON for the PR number, then calls `GET /repos/{repo}/pulls/{pr}/files` and filters for `.proto`.
3. `extract_guide_text` walks every page of the PDF with PyPDF2 and concatenates the text.
4. For each changed proto, `analyze_proto_diff` builds a system + user message pair containing the guide text, a strict output format, and the `git diff` output, then POSTs to `http://localhost:11434/api/chat` with `stream: false` and reads `message.content` from the response.
5. Feedback for all files is concatenated under one heading, a fixed summary line is appended, and `post_comment` POSTs it to `/repos/{repo}/issues/{pr}/comments`.

Known rough edges worth knowing before you rely on it: a non-200 from Ollama raises and fails the job, all feedback goes in one issue comment rather than inline review comments, and line numbers come from the model reading the diff rather than from any parser, so they can drift.

## License

MIT. See [LICENSE](LICENSE).
