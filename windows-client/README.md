# 107 Dashboard Windows Client

The Windows client connects each user to their own 107 Unix account, installs or updates the
Linux Dashboard package, starts the loopback-only service, creates a local SSH tunnel, and opens
the web interface.

## Runtime Flow

```text
Windows EXE
  -> SSH public key + keyboard-interactive verification
  -> Linux environment check
  -> versioned SFTP upload when required
  -> SHA-256 verification and install
  -> tmux service on remote 127.0.0.1:<dynamic port>
  -> local 127.0.0.1:<dynamic port> SSH tunnel
  -> /107-dashboard/ in the default browser
```

The client stores the host, port, username, private-key path, and accepted SSH host fingerprint
under `%LocalAppData%/107Dashboard`. It does not store the private-key passphrase, verification
code, private key contents, or a TOTP secret.

The first install or an update opens a second SSH authentication exchange for SFTP. A normal
launch of an already installed matching version uses one SSH connection.

## Build

Install the .NET 8 SDK, Python 3.12 backend environment, and frontend dependencies. From the
repository root run:

```powershell
$env:DOTNET_EXE = "$env:USERPROFILE\.dotnet\dotnet.exe"
backend/.venv/Scripts/python.exe scripts/build-windows-client.py
```

Use `--skip-frontend-build` only when `frontend/dist/` already contains a validated
`/107-dashboard/` production build. Use `--require-clean` for a formal team release. The ignored
`data/releases/` directory receives one self-contained `win-x64` EXE and its SHA-256 file.

## Current Validation Boundary

The client build, three core unit tests, embedded-payload check, process startup, and desktop UI
layout have passed locally. Authentication against the real 107 keyboard-interactive flow,
remote installation, dynamic remote port use, and tunnel access still require an account owner
to complete an interactive platform acceptance run.

The trial EXE is not code-signed and may trigger Windows SmartScreen. A formal public distribution
should be signed with the team's trusted code-signing certificate when one is available.

The remote service binds only to loopback. Whether the platform permits persistent login-node
web services and which remote port range is approved remain organizer decisions; the client
keeps the port dynamic so that policy can be replaced without changing the web application.
