# Linux Release Package

The release archive contains the Python backend, a prebuilt `/107-dashboard/` frontend,
deployment helpers, tests, sanitized fixtures, and acceptance projects. It never includes
runtime data, virtual environments, Node dependencies, Git metadata, or private environment
files.

## Build on Windows or Linux

From the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/build-release.py
```

For a formal release, require a clean working tree:

```powershell
backend/.venv/Scripts/python.exe scripts/build-release.py --require-clean
```

Archives and SHA-256 files are written to the ignored `data/releases/` directory.

## Install on the Linux Slurm Platform

```bash
sha256sum -c 107dashboard-*.tar.gz.sha256
tar -xzf 107dashboard-*.tar.gz
cd 107dashboard-*
bash deploy/release/install.sh
```

The installer requires Python 3.12, Git, tmux, and native `sbatch`, `scancel`, `squeue`, and
`sacct` commands. It installs Python dependencies from the configured package index, runs the
backend checks, installs acceptance projects when absent, writes a private Native configuration,
and starts the existing single-worker tmux service.

Use `--no-start` to prepare without starting, `--skip-tests` to skip pytest, or
`--refresh-test-projects` to back up and replace existing acceptance projects.

The standalone installer leaves the service bound to `127.0.0.1:8000`. The Windows client may
replace the port with a dynamically selected loopback port and reach it through its authenticated
SSH tunnel. A protected reverse proxy is required only when the platform provides a shared URL
instead of per-user SSH tunnel access.
