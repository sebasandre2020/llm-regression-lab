# LLM Regression Lab

## Authorized next step

The user selected proposal 5 from an AI engineering portfolio roadmap and asked to proceed in a NEW Codex chat in a NEW local project, preserving the original planning chat. Start Phase 2 here once this folder is registered as a local project. Do not require selection of three more projects.

## Product

A production-grade, consumable evaluation service for CI. Accept versioned evaluation jobs and return comparable quality, latency, and cost reports for prompt, model, and retrieval changes. Keep the scope bounded and service-first; any TypeScript frontend must be only a minimal developer testbench. Target AI Engineer, LLM Systems Engineer, Backend AI Engineer, and Applied AI Systems Architect portfolio roles.

Repository root: `C:\Repositories\GHProjects\llm-regression-lab`.

Stack: Python, FastAPI, AsyncIO, Pydantic v2, OpenAPI 3.1, promptfoo, Ragas, PostgreSQL, AWS S3 and ECS Fargate tasks, Langfuse datasets/traces, Docker, Terraform, and GitHub Actions. Use additional technologies only when justified by this service's needs.

AI capability: prompt and RAG regression evaluation combining deterministic assertions, retrieval metrics, and calibrated model-based judgments.

Backend capability: immutable dataset/configuration identifiers, asynchronous jobs, bounded evaluator concurrency, and CI gates that distinguish quality regressions from infrastructure failures.

## Phase 2 deliverables

Create concrete architectural and documentation scaffolding in this repository. This phase is the full technical blueprint, not an instruction to provision paid cloud infrastructure or claim a live deployment.

1. Production infrastructure and CI/CD blueprint: AWS deployment strategy, Terraform setup, and GitHub Actions steps for linting, static analysis, unit/integration/evaluation tests, container build, and cloud deployment. Document required credentials and deployment controls.
2. `README.md`: concise recruiter introduction, architecture, API consumption examples, measured metrics when available, and documentation links. Clearly label endpoints and performance targets that are not yet implemented or measured.
3. `Architecture.md`: Mermaid topology, request/job lifecycle, state transitions, security boundaries, and data flow.
4. `Class.md`: Mermaid class/state diagrams, evaluator and provider adapters, justified design patterns, and persistence models.
5. `Index.md`: categorized map of API endpoints, workers, tools, and background processes to their detailed documentation.
6. `docs/api/` and `docs/services/`: detailed payload schemas, contracts, error codes, idempotency semantics, and proposed latency/SLO targets.
7. `Operations.md`: local Docker Compose runbook, telemetry including Langfuse and relevant system metrics, evaluation triggers, failure recovery, and operational procedures. Distinguish working commands from planned ones.

Resolve routine design choices autonomously. Inspect applicable AGENTS.md files, current official technology documentation, and the repository before authoring. Do not invent performance results, working infrastructure, credentials, or completed implementation.

## Market grounding from Phase 1

Source: https://docs.google.com/spreadsheets/d/1_cpov-r0tzpV51dMkB9nRYqUH5EiWzBAZSCs-YUCXNY/edit?gid=1669046147#gid=1669046147

Read-only analysis found 66 job rows and one duplicated URL. The systems cohort comprised 58 unique postings in rows 2-60 after deduplicating the integration role; the AI cohort comprised 22 postings. Strong signals: Python, APIs, SQL, AWS, production reliability, retrieval, orchestration, and evaluation. Evaluation/benchmarking/monitoring appeared in 11 of 22 AI postings. LangSmith appeared in 3, Langfuse in 2, and promptfoo in 2. Ragas, Fargate, Pydantic v2, and OpenAPI were portfolio architecture choices, not explicit matrix requirements.

## Starting instruction for the new chat

Read PROJECT_BRIEF.md and execute Phase 2 for LLM Regression Lab. Create the technical blueprints and documentation scaffolding in this project. Keep subsequent project work in this new chat and leave the original portfolio-planning chat intact.
