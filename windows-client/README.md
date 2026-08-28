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

The portable client stores the host, port, username, private-key path, and accepted SSH host
fingerprint in `data/client-settings.json` next to the EXE. When this is the first launch of a
portable copy and the legacy `%LocalAppData%/107Dashboard/client-settings.json` exists, the client
imports it once and continues using the portable copy. It does not store the private-key passphrase,
verification code, private key contents, or a TOTP secret.

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
`data/releases/` receives a self-contained `win-x64` EXE, a portable ZIP containing the EXE and
empty `data/` directory, and a SHA-256 file for each artifact. Keep `data/` when replacing a
portable client with a newer ZIP.

## 快速预览界面

界面调试不需要先发布 EXE。仓库根目录执行下面的命令，会直接以 Debug 配置启动 WPF
窗口；它只使用 `bin/` 和 `obj/` 中的构建缓存，不会写入 `data/`，也不会替换便携版客户端：

```powershell
.\scripts\run-windows-client.ps1
```

如果本机没有把 `dotnet.exe` 加入 PATH，可以先指定 SDK 路径：

```powershell
$env:DOTNET_EXE = "$env:USERPROFILE\.dotnet\dotnet.exe"
.\scripts\run-windows-client.ps1
```

也可以直接打开 `windows-client/107Dashboard.Client.sln`，按 F5 启动并调试。修改
`MainWindow.xaml` 后重新启动即可观察布局；只有需要交付给用户时才运行上面的发布构建命令。

Remote updates are installed into immutable version directories. The client switches `current`
only after installation and startup succeed, keeps `previous` for rollback, and removes releases
older than those two versions. Runtime data remains under the remote `runtime/` directory.

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
