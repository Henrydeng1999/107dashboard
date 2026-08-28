# 107 Dashboard Windows Client

The Windows client connects each user to their own 107 Unix account, installs or updates the
Linux Dashboard package, starts the loopback-only service, creates a local SSH tunnel, and loads
the remote web interface inside its own window. The client is a desktop shell and connection
controller; jobs, logs, history, and AI data remain on 107 and are read through the tunnel.

## Runtime Flow

```text
Windows EXE
  -> SSH public key + keyboard-interactive verification
  -> Linux environment check
  -> versioned SFTP upload when required
  -> SHA-256 verification and install
  -> tmux service on remote 127.0.0.1:<dynamic port>
  -> local 127.0.0.1:<dynamic port> SSH tunnel
  -> /107-dashboard/ in the embedded WebView2 window
```

The EXE requires the Microsoft Edge WebView2 Runtime, which is normally already present on
supported Windows 10 and Windows 11 installations. If it is missing, the client keeps the SSH
connection flow intact and displays an actionable error in the main window instead of silently
opening another browser.

The portable client stores the host, port, username, private-key path, and accepted SSH host
fingerprint in `data/client-settings.json` next to the EXE. Deployment metadata is stored in
`data/deployment-cache.json`. When this is the first launch of a
portable copy and the legacy `%LocalAppData%/107Dashboard/client-settings.json` exists, the client
imports it once and continues using the portable copy. It does not store the private-key passphrase,
verification code, private key contents, or a TOTP secret.

The first install or an update opens a second SSH authentication exchange for SFTP. After a
successful connection, the client writes non-sensitive deployment metadata to
`data/deployment-cache.json`. A normal launch for the same host, port, account, and embedded
service release uses one SSH connection and a lightweight remote service probe; it skips the
full environment and version scan. If that probe fails, the cache is deleted and the original
full check and recovery path runs automatically. The update button always bypasses this cache.
The cache does not contain a password, verification code, private-key data, or TOTP secret.

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

The desktop window has a service toolbar for update, service logs, connection settings, and
remote stop/disconnect. Closing or minimizing the window does not stop the remote service when
the client is still connected: minimizing hides the window to the system tray, where it can be
restored or exited. Choosing `退出` closes the WebView2 page, SSH tunnel, and SSH connection;
it does not remove the remote installation. The tray and window use the bundled
`Assets/107dashboard.ico` logo.

WebView2 profile data is stored next to the EXE at `data/webview2`. Connection settings remain
in `data/client-settings.json`, and the deployment cache is in `data/deployment-cache.json`;
keep the complete `data/` directory when replacing the EXE or extracting a newer portable ZIP.

## Current Validation Boundary

The client build, nine core unit tests, embedded-payload check, process startup, and desktop UI
layout have passed locally. Authentication against the real 107 keyboard-interactive flow,
remote installation, dynamic remote port use, WebView2 page loading, and tunnel access still
require an account owner to complete an interactive platform acceptance run.

The trial EXE is not code-signed and may trigger Windows SmartScreen. A formal public distribution
should be signed with the team's trusted code-signing certificate when one is available.

The remote service binds only to loopback. Whether the platform permits persistent login-node
web services and which remote port range is approved remain organizer decisions; the client
keeps the port dynamic so that policy can be replaced without changing the web application.
