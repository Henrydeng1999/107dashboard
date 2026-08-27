using System.Globalization;
using System.Text;
using Dashboard107.Client.Models;
using Renci.SshNet;

namespace Dashboard107.Client.Services;

public sealed class RemoteDeploymentService
{
    private const string RemoteRoot = ".local/share/107dashboard";

    public async Task<string> CheckEnvironmentAsync(
        SshClient client,
        CancellationToken cancellationToken = default)
    {
        const string script = """
            set -e
            if command -v python3.12 >/dev/null 2>&1; then
              PYTHON_BIN="$(command -v python3.12)"
            elif [ -x /public/app/python3.12/3.12/bin/python3 ]; then
              PYTHON_BIN=/public/app/python3.12/3.12/bin/python3
            else
              echo '缺少 Python 3.12' >&2
              exit 10
            fi
            for command in git tmux sbatch scancel squeue sacct sha256sum tar; do
              command -v "$command" >/dev/null 2>&1 || { echo "缺少命令: $command" >&2; exit 11; }
            done
            printf 'PYTHON_BIN=%s\nUSER=%s\nHOME=%s\n' "$PYTHON_BIN" "$(id -un)" "$HOME"
            """;
        return await RunCheckedAsync(client, Bash(script), cancellationToken);
    }

    public async Task<RemoteDashboardState> GetStateAsync(
        SshClient client,
        CancellationToken cancellationToken = default)
    {
        const string script = """
            ROOT="$HOME/.local/share/107dashboard"
            if [ ! -L "$ROOT/current" ] || [ ! -f "$ROOT/current/VERSION" ]; then
              echo 'INSTALLED=false'
              exit 0
            fi
            echo 'INSTALLED=true'
            printf 'RELEASE_ID=%s\n' "$(basename "$(readlink "$ROOT/current")")"
            sed -n 's/^version=/VERSION=/p; s/^commit=/COMMIT=/p' "$ROOT/current/VERSION"
            sed -n 's/^APP_PORT=/PORT=/p' "$ROOT/current/data/107dashboard.env" 2>/dev/null || true
            if tmux has-session -t '=107dashboard' 2>/dev/null; then
              echo 'RUNNING=true'
            else
              echo 'RUNNING=false'
            fi
            """;
        var result = await RunAsync(client, Bash(script), cancellationToken);
        var values = ParseKeyValues(result.Output);
        var installed = values.GetValueOrDefault("INSTALLED") == "true";
        var running = values.GetValueOrDefault("RUNNING") == "true";
        var releaseId = values.GetValueOrDefault("RELEASE_ID", string.Empty);
        int? port = int.TryParse(values.GetValueOrDefault("PORT"), out var parsedPort)
            ? parsedPort
            : null;
        return new RemoteDashboardState(installed, running, releaseId, port, result.Combined);
    }

    public async Task<string> DeployAsync(
        SshClient sshClient,
        SftpClient sftpClient,
        ReleasePackage package,
        IProgress<double>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var info = package.Info;
        await RunCheckedAsync(
            sshClient,
            Bash("mkdir -p \"$HOME/.local/share/107dashboard/packages\" \"$HOME/.local/share/107dashboard/releases\" \"$HOME/.local/share/107dashboard/runtime\""),
            cancellationToken);

        var remoteArchive = $"{sftpClient.WorkingDirectory.TrimEnd('/')}/{RemoteRoot}/packages/{info.ReleaseId}.tar.gz";
        using (var content = package.OpenRead())
        {
            await Task.Run(
                () => sftpClient.UploadFile(
                    content,
                    remoteArchive,
                    true,
                    uploaded => progress?.Report((double)uploaded / content.Length)),
                cancellationToken);
        }

        var releaseId = ShellQuote.Posix(info.ReleaseId);
        var archiveRoot = ShellQuote.Posix(info.ArchiveRoot);
        var checksum = ShellQuote.Posix(info.Sha256);
        var script = $$"""
            set -euo pipefail
            ROOT="$HOME/.local/share/107dashboard"
            RELEASE_ID={{releaseId}}
            ARCHIVE_ROOT={{archiveRoot}}
            EXPECTED_SHA={{checksum}}
            ARCHIVE="$ROOT/packages/$RELEASE_ID.tar.gz"
            TARGET="$ROOT/releases/$RELEASE_ID"
            ACTUAL_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
            [ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] || { echo '服务包 SHA-256 校验失败' >&2; exit 20; }
            if [ ! -d "$TARGET" ]; then
              STAGE="$(mktemp -d "$ROOT/releases/.staging-XXXXXX")"
              trap 'rm -rf "$STAGE"' EXIT
              tar -xzf "$ARCHIVE" -C "$STAGE"
              [ -d "$STAGE/$ARCHIVE_ROOT" ] || { echo '服务包顶层目录不正确' >&2; exit 21; }
              mv "$STAGE/$ARCHIVE_ROOT" "$TARGET"
            fi
            if [ ! -e "$TARGET/data" ]; then
              ln -s "$ROOT/runtime" "$TARGET/data"
            fi
            if command -v python3.12 >/dev/null 2>&1; then
              PYTHON_BIN="$(command -v python3.12)"
            else
              PYTHON_BIN=/public/app/python3.12/3.12/bin/python3
            fi
            PYTHON_BIN="$PYTHON_BIN" bash "$TARGET/deploy/release/install.sh" --no-start
            PREVIOUS="$(readlink "$ROOT/current" 2>/dev/null || true)"
            if [ -x "$ROOT/current/scripts/107-dashboard-service.sh" ]; then
              bash "$ROOT/current/scripts/107-dashboard-service.sh" stop || true
            fi
            ln -sfnT "$TARGET" "$ROOT/current"
            PORT="$($PYTHON_BIN - <<'PY'
            import socket
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                print(listener.getsockname()[1])
            PY
            )"
            sed -i -E "s/^APP_PORT=.*/APP_PORT=$PORT/" "$TARGET/data/107dashboard.env"
            if ! bash "$ROOT/current/scripts/107-dashboard-service.sh" start; then
              if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
                ln -sfnT "$PREVIOUS" "$ROOT/current"
                bash "$ROOT/current/scripts/107-dashboard-service.sh" start || true
              fi
              echo '新版本启动失败，已尝试恢复上一版本' >&2
              exit 22
            fi
            printf 'DEPLOYED=%s\nPORT=%s\n' "$RELEASE_ID" "$PORT"
            """;
        return await RunCheckedAsync(sshClient, Bash(script), cancellationToken);
    }

    public async Task<int> EnsureStartedAsync(
        SshClient client,
        CancellationToken cancellationToken = default)
    {
        const string script = """
            set -euo pipefail
            ROOT="$HOME/.local/share/107dashboard"
            [ -x "$ROOT/current/scripts/107-dashboard-service.sh" ] || { echo '服务尚未安装' >&2; exit 30; }
            if ! tmux has-session -t '=107dashboard' 2>/dev/null; then
              bash "$ROOT/current/scripts/107-dashboard-service.sh" start
            fi
            PORT="$(sed -n 's/^APP_PORT=//p' "$ROOT/current/data/107dashboard.env")"
            case "$PORT" in (*[!0-9]*|'') echo '远程服务端口无效' >&2; exit 31;; esac
            printf 'PORT=%s\n' "$PORT"
            """;
        var output = await RunCheckedAsync(client, Bash(script), cancellationToken);
        var values = ParseKeyValues(output);
        return int.TryParse(values.GetValueOrDefault("PORT"), out var port)
            ? port
            : throw new InvalidOperationException("未能读取远程服务端口。");
    }

    public Task<string> StopAsync(SshClient client, CancellationToken cancellationToken = default) =>
        RunCheckedAsync(
            client,
            Bash("ROOT=\"$HOME/.local/share/107dashboard\"; [ -x \"$ROOT/current/scripts/107-dashboard-service.sh\" ] && bash \"$ROOT/current/scripts/107-dashboard-service.sh\" stop"),
            cancellationToken);

    public Task<string> LogsAsync(SshClient client, CancellationToken cancellationToken = default) =>
        RunCheckedAsync(
            client,
            Bash("ROOT=\"$HOME/.local/share/107dashboard\"; [ -x \"$ROOT/current/scripts/107-dashboard-service.sh\" ] && bash \"$ROOT/current/scripts/107-dashboard-service.sh\" logs"),
            cancellationToken);

    private static string Bash(string script) => $"bash -lc {ShellQuote.Posix(script)}";

    private static async Task<string> RunCheckedAsync(
        SshClient client,
        string command,
        CancellationToken cancellationToken)
    {
        var result = await RunAsync(client, command, cancellationToken);
        if (result.ExitStatus != 0)
        {
            throw new InvalidOperationException(
                $"远程命令失败（退出码 {result.ExitStatus}）。\n{result.Combined}".Trim());
        }

        return result.Output;
    }

    private static async Task<CommandResult> RunAsync(
        SshClient client,
        string command,
        CancellationToken cancellationToken)
    {
        return await Task.Run(
            () =>
            {
                using var remote = client.CreateCommand(command, Encoding.UTF8);
                remote.CommandTimeout = TimeSpan.FromMinutes(10);
                var output = remote.Execute();
                return new CommandResult(remote.ExitStatus ?? -1, output, remote.Error);
            },
            cancellationToken);
    }

    private static Dictionary<string, string> ParseKeyValues(string output)
    {
        return output.Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Select(line => line.TrimEnd('\r'))
            .Select(line => line.Split('=', 2))
            .Where(parts => parts.Length == 2)
            .ToDictionary(parts => parts[0], parts => parts[1], StringComparer.Ordinal);
    }

    private sealed record CommandResult(int ExitStatus, string Output, string Error)
    {
        public string Combined => string.Join(
            Environment.NewLine,
            new[] { Output.Trim(), Error.Trim() }.Where(value => value.Length > 0));
    }
}
