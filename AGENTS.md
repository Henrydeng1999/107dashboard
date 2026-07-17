# AGENTS.md

## Project

107 Dashboard is a competition MVP for student-facing Slurm job management and visualization.

The product flow is:

```text
configure job
  -> submit to Slurm
  -> view queue and runtime status
  -> inspect stdout/stderr logs
  -> cancel or clone a job
  -> view basic resource usage
```

AI is used to assist the team with development, documentation, testing, and debugging. AI is not a runtime product feature.

## Read First

Before changing code or documentation, read:

1. `README.md`
2. `docs/01-PLAN.md`
3. `docs/02-ARCHITECTURE.md`
4. `docs/03-ENVIRONMENT_CHECK.md`
5. `docs/04-COLLABORATION.md`
6. `docs/05-DIRECTORY-STRUCTURE.md`
7. `docs/06-PLATFORM-DEPLOYMENT.md`

## Current Scope

Prioritize a complete and demonstrable competition workflow. Do not block the MVP on production concerns such as campus SSO, true multi-user Slurm delegation, PostgreSQL, Rootless Docker, or production HTTPS.

The default prototype deployment is:

```text
prebuilt React static files
  -> FastAPI/Uvicorn in a project Python virtual environment
  -> native Slurm commands on the platform
  -> SQLite for prototype metadata
```

## Repository Boundaries

- `backend/app/api/routes/`: HTTP endpoints only.
- `backend/app/schemas/`: validated request and response models.
- `backend/app/services/`: application workflows.
- `backend/app/slurm/`: controlled Slurm command execution and output parsing.
- `backend/app/repositories/`: persistence access.
- `backend/app/models/`: database models.
- `backend/app/core/`: configuration, logging, and shared infrastructure.
- `frontend/src/features/jobs/`: job-domain UI and state.
- `frontend/src/components/`: genuinely reusable UI components.
- `fixtures/`: sanitized Slurm output and job log samples.
- `examples/`: public and sanitized example job scripts.
- `scripts/`: platform inspection and maintenance scripts.
- `deploy/`: user service and optional proxy configuration.

Do not create new top-level directories without updating `docs/05-DIRECTORY-STRUCTURE.md` and explaining the ownership boundary.

## Platform Facts

- Login node: Ubuntu 24.04.3, Python 3.12.3.
- Python `venv`, `pip`, SQLite, Git, GCC, and Make are available.
- Node.js is not installed on the platform; build the frontend locally or in CI.
- Slurm 25.11.2 commands are available natively.
- Verified combination: partition `Students`, account `stu`, QoS `qos_stu_default`.
- `qos_stu_default` permits up to 4 CPUs, 1 GPU, 16 GiB memory, and 4 hours per job.
- A real test job completed on an RTX 5090 node.
- The login node must not run student compute workloads directly.
- System Docker is not available to the user and Rootless Docker is not configured.
- User systemd is available, but linger is disabled. tmux may be used for development/demo process persistence only.

See `docs/03-ENVIRONMENT_CHECK.md` for the complete verified environment record.

## Slurm Safety

- Never execute student compute workloads on the login node.
- Submit compute work through `sbatch` or an approved Slurm operation.
- Never concatenate unvalidated user input into shell commands.
- Model partition, QoS, CPU, memory, GPU, time limit, command, and paths as validated fields.
- Treat Slurm and `sacct` as the source of truth for job state.
- Validate ownership before reading logs, cancelling, cloning, or exposing job details.
- Use mock fixtures for local development and tests whenever real Slurm access is unnecessary.
- Keep real resource requests minimal when performing platform checks.
- The competition Native prototype uses one trusted Unix-account identity: derive it from the backend process effective UID and assert it matches deployment configuration. Never accept a Slurm username from HTTP input.
- Keep Native jobs API fail closed until OS-identity startup validation, persisted owner metadata, and per-operation ownership checks are implemented and tested.

## Security

- Never commit passwords, TOTP secrets, SSH private keys, access tokens, cookies, or production credentials.
- Do not commit real user logs or unredacted paths belonging to other users.
- Do not mount or expose the Docker socket, SSH ControlMaster socket, or private keys to the application.
- Runtime data, logs, SQLite files, generated job scripts, virtual environments, and frontend build output must remain outside tracked source files.

## Development Rules

- Follow the existing directory structure and keep changes scoped.
- Prefer a vertical, demonstrable feature slice over isolated large subsystems.
- Keep `master` runnable and suitable for the current demo.
- Add or update tests in proportion to behavior changes.
- Update documentation when changing architecture, platform assumptions, APIs, or directory ownership.
- Use structured parsers and subprocess argument arrays instead of shell string construction.
- Avoid premature abstractions and production-only infrastructure during the competition MVP.

## Git Workflow

- Use short-lived branches such as `feature/job-submit`, `feature/slurm-adapter`, or `fix/log-tail`.
- Link nontrivial work to a Gitee Issue with acceptance criteria.
- Use focused commits such as `feat:`, `fix:`, `docs:`, `test:`, and `chore:`.
- Use Pull Requests for feature code and request at least one teammate review.
- Do not rewrite or discard another member's uncommitted work.

### Parallel development rules

- Keep `master` runnable and demonstrable. During the current bootstrap phase, the project administrator may develop directly on `master`; once parallel contributors join, switch to feature branches and PRs.
- Create each feature branch from the latest `master`, and keep one branch focused on one feature.
- Prefer directory ownership: frontend work in `frontend/src/`, backend workflow work in `backend/app/api/`, `services/`, `schemas/`, and `repositories/`, Slurm work in `backend/app/slurm/`, and tests/deployment work in `backend/tests/`, `tests/e2e/`, and `deploy/`.
- Before parallel implementation, agree on API paths, request/response fields, status codes, and error formats. Frontend may use fixtures or Mock data, but its types must match the agreed API.
- Avoid concurrent edits to shared files such as `README.md`, `package.json`, `backend/app/main.py`, global styles, and the same documentation section. Announce shared-file changes before editing.
- Keep commits small and sync long-lived branches with `master` regularly. Do not rebase a branch already being used by others without agreement.
- A PR must state the related task, changed behavior, dependencies, test commands/results, and known risks. Merge only after at least one teammate review and relevant checks pass.
- Prefer squash merge for completed feature branches so `master` keeps a clear history.
- When conflicts occur, inspect and resolve them manually, preserve both sides where required, and rerun tests. Never use `git reset --hard`, `git checkout -- .`, or bulk deletion to discard another member's work.

### Progress checklist maintenance

- `docs/08-PROGRESS-CHECKLIST.md` is the project status source for reviewers and must stay synchronized with delivered behavior.
- Whenever an Agent prepares, reviews, or merges a Pull Request into `master`, it must update the checklist in the same PR before merge if the PR changes feature status, verification evidence, milestones, blockers, or the next development item.
- During the administrator-only bootstrap exception, apply the same rule before a direct milestone commit to `master`.
- Mark an item complete only after the relevant test, build, parser fixture, or platform evidence has passed. Do not infer completion from files existing or code being partially implemented.
- Update the visible date, phase counts, completed-function table, current limitations, and next task where applicable. Keep `docs/index.html`, `docs/site.js`, and documentation chapter counts consistent when the progress document structure changes.
- If a PR does not affect progress, state that explicitly in the PR review summary; do not make cosmetic checklist edits solely to touch the file.

## Verification

Before handing off a change:

1. Run the relevant formatter, linter, and tests when available.
2. Verify that no secrets or runtime artifacts are staged.
3. Confirm documentation links and directory references remain valid.
4. For Slurm changes, test parsers with fixtures before using the real platform.
5. When a real Slurm check is required, report Job ID, requested resources, state, exit code, and collected evidence.

If project commands do not exist yet, do not invent conflicting toolchains. Add the minimum required configuration and document the chosen command in `README.md`.
