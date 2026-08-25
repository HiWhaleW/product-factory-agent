<h1 align="center">Product Factory Agent</h1>

<p align="center">
  A local-first, AI-native product delivery agent.<br>
  Describe what you want to build, and the agents coordinate context, tools, artifacts, reviews, and human-controlled gates.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/AI--Native-Agent%20Product-0B57D0?style=flat-square" alt="AI Native Agent Product">
  <img src="https://img.shields.io/badge/Next.js-16-111111?style=flat-square&logo=nextdotjs" alt="Next.js 16">
  <img src="https://img.shields.io/badge/FastAPI-0.141-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/deployment-local--first-D6A313?style=flat-square" alt="Local first">
  <img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-D84A3A?style=flat-square" alt="PolyForm Noncommercial License 1.0.0">
</p>

<p align="center">
  <a href="#overview"><strong>Overview</strong></a>
  ·
  <a href="#release-status"><strong>Release status</strong></a>
  ·
  <a href="#run-locally"><strong>Run locally</strong></a>
  ·
  <a href="#license"><strong>License</strong></a>
</p>

> [!NOTE]
> Product Factory Agent is a local web application. The Web app, API, PostgreSQL database, project files, and user credentials run on the user's own computer. After startup, open `http://127.0.0.1:3400`. This project is not a hosted public SaaS service.

> [!WARNING]
> The product does not bundle an LLM or web-search API. Each user configures their own providers in Settings. When a required provider is missing, the relevant agent task stops explicitly instead of using a hidden maintainer key or fabricating a result.

> [!IMPORTANT]
> Only the user can approve a product gate. The model cannot advance a business stage, expand tool permissions, publish code, or delete a project workspace on its own.

## Release status

The following state was verified when the complete source baseline was published on August 25, 2026:

| Area | Current state |
| --- | --- |
| Local source preview | Web `127.0.0.1:3400` and API `127.0.0.1:8400` are healthy; Alembic is at `20260824_0011 (head)`; no user model API is configured. |
| Local Git | `main` contains the cleaned source baseline. Runtime data, external archives, and internal agent instructions are excluded. |
| GitHub repository | `HiWhaleW/product-factory-agent` `main` contains the complete source, installation scripts, tests, documentation, and `LICENSE`. The repository is currently private and can only be cloned by authorized accounts. |
| Publication | The complete source was merged through [PR #2](https://github.com/HiWhaleW/product-factory-agent/pull/2) without including local runtime data or historical archives. |
| Historical baseline | The older user-beta PR from August 24, 2026 is not the current source baseline and must not overwrite `main`. |
| Compose installation | The installation contract and scripts are implemented, but real image builds and clean-machine installation have not yet been validated because the maintainer's computer has no compatible container runtime. |

In short: the complete source is on GitHub `main`, the source-based local application and automated checks pass, and real Docker Compose installation remains unverified. While the repository is private, external users cannot download it. Once public, users can install it on their own computers and access it through a browser.

## Overview

Product Factory Agent is not a fixed workflow with a chat box attached. It is designed around agents that carry out product work while deterministic controls preserve ownership, permissions, evidence, and user authority.

After a user describes a product goal in natural language, the system can:

1. Understand the goal, identify missing information, and ask scope questions.
2. Turn confirmed facts into structured context.
3. Let the lead agent create tasks and provide specialist agents with the minimum required context.
4. Call tools within explicit permission, budget, and product-gate constraints.
5. Produce persistent, traceable, versioned artifacts.
6. Use an independent reviewer to inspect evidence, scope, risk, and acceptance results.
7. Return every decision to continue to the user.
8. Preserve records and recover after edits, failures, or interruptions.

A chat message is not an artifact, and a model saying “done” is not completion. Delivery requires real artifacts, tool results, test evidence, reviewer conclusions, and user-approved gates.

## Current capabilities

- Local account registration, password login, and HttpOnly sessions
- Per-user isolation for projects, messages, tasks, runs, gates, artifacts, and provider settings
- Natural-language project entry, project list, project chat, and artifact workspace
- Factory Lead, AI PM, Builder, and Reviewer agents
- Twelve product stages and G0–G6 human-controlled gates
- Context Version, Context Pack, Agent Task, RunStep, and recovery records
- Separate user-visible Artifact DAG and internal Execution Task DAG
- OpenAI-compatible model configuration
- Runtime integration for the official Bocha web-search API
- Per-user local Secret Store with `0600` permissions
- Docker Compose v2 installation, backup, restore, upgrade, rollback, and uninstall scripts

The current release does not provide a public SaaS service, bundled model credits, bundled search credits, payments, automatic Git pushes, automatic cloud deployment, or unrestricted host access for Builder.

## AI-native execution loop

```text
Natural-language goal
→ Lead agent understanding and clarification
→ Structured context
→ User gate
→ Agent task and minimum Context Pack
→ Governed tool calls
→ Persistent artifacts and RunSteps
→ Independent reviewer
→ User decision to continue, revise, pause, or stop
```

AI handles ambiguous-language understanding, planning, candidate generation, evidence comparison, and feedback interpretation. The deterministic control plane owns identity, state transitions, gates, permissions, budgets, idempotency, auditing, and recovery.

## Core product experience

| Capability | What the user gets |
| --- | --- |
| Natural-language project creation | No need to translate an idea into a complex form or rigid template first. |
| Proactive clarification | The lead agent asks questions where missing information materially changes scope. |
| Multi-agent collaboration | Each specialist receives a concrete task and the minimum required context instead of merely role-playing. |
| Cumulative artifact workspace | MRDs, PRDs, designs, technical documents, code, and QA evidence accumulate with versions and dependencies. |
| Human-controlled gates | The user decides every critical business transition; agents cannot approve on the user's behalf. |
| Independent review | Review inputs, evidence, and conclusions are separated from the generating agent. |
| Recoverable execution | RunSteps, tool results, and idempotency data survive failures and interruptions. |
| Bring your own API | Every local user configures and owns their model and search credentials. |

## AI and deterministic responsibilities

| AI is responsible for | Deterministic code is responsible for |
| --- | --- |
| Understanding ambiguous natural language | Validating schemas and user identity |
| Asking clarification questions and proposing plans | Enforcing the allowed state transition |
| Recommending tool calls | Applying `allow / ask / deny` tool policy |
| Producing candidate documents, designs, or code | Persisting artifacts, versions, hashes, and dependencies |
| Comparing evidence and drafting reviews | Validating evidence references, budgets, idempotency, and recovery conditions |
| Interpreting feedback and proposing revisions | Accepting gate decisions only from the user |

Model output is not the source of truth and cannot bypass sessions, gates, tool policy, artifact validation, or review.

## Run locally

> [!CAUTION]
> The commands below are the installation entry point once the repository is public. While it remains private, only authorized GitHub accounts can clone it. Repository visibility is controlled separately by the maintainer.

### Requirements

- Git
- A compatible container runtime that exposes the Docker Engine API
- Docker Compose v2, available through `docker compose version`
- At least 4 GB of available memory and 10 GB of free disk space
- `bash`, `openssl`, `curl`, and `shasum`
- Local port `3400` available

Docker Desktop is not part of this project. Users on macOS, Windows, or Linux may choose any compatible Docker Engine and Compose v2 runtime.

### Install

```bash
git clone https://github.com/HiWhaleW/product-factory-agent.git
cd product-factory-agent
./scripts/install/install.sh
```

After installation, open:

```text
http://127.0.0.1:3400
```

Create the first local account on first launch. The first account becomes the local administrator. A fresh installation starts with an empty project list and no model or search API configuration.

Common operations:

```bash
./scripts/install/health.sh
./scripts/install/backup.sh
./scripts/install/stop.sh
./scripts/install/start.sh
./scripts/install/upgrade.sh
./scripts/install/rollback.sh
./scripts/install/uninstall.sh
```

See [Local installation](docs/installation.md) for backup, restore, upgrade, rollback, and destructive-operation boundaries.

## Architecture

- Next.js 16 / React 19 / Tailwind CSS 4
- FastAPI / Pydantic / SQLAlchemy
- PostgreSQL 16 / Alembic
- Bounded LangGraph agent runs
- AG-UI / SSE event channel
- Factory Lead, AI PM, Builder, and Reviewer
- Deterministic state machine, gates, permissions, and audit control plane
- Local Artifact Store, project workspaces, and per-user Secret Store
- Docker Compose v2 local installation topology

See [Architecture](docs/architecture.md) for the complete design.

## Verification

Locally re-verified on August 25, 2026:

- Web tests: 39/39 passed.
- Python tests: 104 passed / 48 skipped, with one retained Starlette/httpx deprecation warning.
- ESLint, TypeScript, Ruff, and the Next.js production build passed.
- Web and API health checks passed; Alembic is at `20260824_0011 (head)`.
- PostgreSQL integration tests require an isolated temporary database; 48 integration tests remained skipped in the default run.
- Docker Compose installation, real-model behavior, and clean-machine installation have not yet been validated.

```bash
pnpm install --frozen-lockfile
pnpm check
pnpm build
```

PostgreSQL integration tests require a separate temporary test database:

```bash
pnpm test:api:integration
```

Real-model validation requires each user's own API configuration and must be recorded separately from deterministic regression tests.

## Feedback and contributions

Issues, documentation improvements, and pull requests are welcome. While the repository remains private, contribution features are available only to authorized GitHub accounts. Once public, anyone who follows the license and contribution requirements may participate.

- Report usage problems, bugs, or feature requests through [Issues](https://github.com/HiWhaleW/product-factory-agent/issues).
- Submit fixes and improvements through [Pull Requests](https://github.com/HiWhaleW/product-factory-agent/pulls).
- Describe the problem, scope, verification results, and known limitations in every PR.
- Include desktop and mobile screenshots or a reviewable recording for UI changes.
- Never include API keys, cookies, database connection strings, logs containing secrets, or real user data in issues, PRs, screenshots, or test fixtures.
- A PR is a code proposal only. Merging, publishing, or changing a product gate remains a maintainer decision.

Suggested contribution flow:

```bash
git checkout -b feature/your-change
pnpm check
pnpm build
git push your-fork feature/your-change
```

Then open a pull request from your fork to this repository.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).

The license permits viewing, using, copying, modifying, and distributing the source for noncommercial purposes, including personal study, research, noncommercial self-use, and creating a fork to contribute a pull request.

Without separate written permission from the copyright holder, the project may not be used in commercial products, paid services, client work, SaaS offerings, advertising, marketing, commercial training, or any other direct or indirect profit-making activity.

You must preserve all notices required by the license when using, copying, or distributing the project. See the repository's `LICENSE` file for the complete legal terms.

Because it includes a noncommercial restriction, this project is **source-available**, not open source under the OSI definition.
