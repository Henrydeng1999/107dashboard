using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Windows;
using Dashboard107.Client.Models;
using Dashboard107.Client.Services;
using Microsoft.Win32;
using Renci.SshNet;

namespace Dashboard107.Client;

public partial class MainWindow : Window
{
    private readonly SettingsStore _settingsStore = new();
    private readonly SshConnectionService _connectionService = new();
    private readonly RemoteDeploymentService _deploymentService = new();
    private ClientSettings _settings;
    private string _privateKeyPath = string.Empty;
    private SshClient? _sshClient;
    private DashboardTunnel? _tunnel;
    private string? _dashboardUrl;
    private string? _acceptedFingerprint;
    private string? _pendingVerificationCode;
    private string? _authenticationStage;
    private DateTime _authenticationDeadlineUtc;

    public MainWindow()
    {
        InitializeComponent();
        _settings = _settingsStore.Load();
        _privateKeyPath = ResolvePrivateKeyPath(_settings.PrivateKeyPath);
        HostTextBox.Text = _settings.Host;
        PortTextBox.Text = _settings.Port.ToString();
        UsernameTextBox.Text = _settings.Username;
        UpdatePrivateKeyDisplay();
        AppendActivity("等待连接 107 平台。");
    }

    private async void ConnectButton_Click(object sender, RoutedEventArgs e) =>
        await ConnectAndOpenAsync(forceDeployment: false);

    private async void UpdateButton_Click(object sender, RoutedEventArgs e) =>
        await ConnectAndOpenAsync(forceDeployment: true);

    private async Task ConnectAndOpenAsync(bool forceDeployment)
    {
        _pendingVerificationCode = ReadPreenteredVerificationCode();
        BeginAuthenticationStage("SSH 主连接");
        SetBusy(true, "正在连接 SSH...");
        try
        {
            Disconnect();
            var options = ReadOptions();
            _acceptedFingerprint = null;
            _sshClient = await _connectionService.ConnectSshAsync(
                options,
                PromptSecret,
                ConfirmHostKey);
            SaveSettings(options);
            ConnectionBadge.Text = "SSH 已连接";
            AppendActivity($"已连接 {options.Username}@{options.Host}:{options.Port}");

            SetStatus("正在检查平台环境...");
            AppendActivity((await _deploymentService.CheckEnvironmentAsync(_sshClient)).Trim());

            var state = await _deploymentService.GetStateAsync(_sshClient);
            ShowRemoteState(state);
            var package = ReleasePackage.LoadEmbedded();
            var needsDeployment = forceDeployment
                || !state.Installed
                || !string.Equals(state.ReleaseId, package.Info.ReleaseId, StringComparison.Ordinal);

            if (needsDeployment)
            {
                SetStatus("正在验证文件传输连接...");
                AppendActivity($"准备部署服务端 {package.Info.ReleaseId}");
                BeginAuthenticationStage("首次安装/更新服务");
                AppendActivity("首次安装或更新服务需要第二次认证，稍后可能再次要求动态验证码。");
                using var sftp = await _connectionService.ConnectSftpAsync(
                    options with { TrustedHostFingerprint = _settings.TrustedHostFingerprint },
                    PromptSecret,
                    ConfirmHostKey);
                var progress = new Progress<double>(value =>
                {
                    ProgressBar.IsIndeterminate = false;
                    ProgressBar.Value = value * 100;
                    StatusText.Text = $"正在上传服务包 {value:P0}";
                });
                AppendActivity((await _deploymentService.DeployAsync(
                    _sshClient,
                    sftp,
                    package,
                    progress)).Trim());
                state = await _deploymentService.GetStateAsync(_sshClient);
                ShowRemoteState(state);
            }

            SetStatus("正在启动远程服务...");
            var remotePort = await _deploymentService.EnsureStartedAsync(_sshClient);
            _tunnel = new DashboardTunnel(_sshClient, remotePort);
            _dashboardUrl = _tunnel.DashboardUrl;
            RemotePortText.Text = remotePort.ToString();
            LocalPortText.Text = _tunnel.LocalPort.ToString();
            ConnectionBadge.Text = "平台可用";
            AppendActivity($"本地入口 {_dashboardUrl}");
            SetConnectedControls(true);
            OpenDashboard();
            SetStatus("平台已连接");
        }
        catch (OperationCanceledException)
        {
            AppendActivity("操作已取消。");
            SetStatus("已取消");
            Disconnect();
        }
        catch (Exception exception)
        {
            AppendActivity(exception.Message);
            SetStatus("连接失败");
            MessageBox.Show(this, exception.Message, "107 Dashboard", MessageBoxButton.OK, MessageBoxImage.Error);
            Disconnect();
        }
        finally
        {
            _pendingVerificationCode = null;
            _authenticationStage = null;
            SetBusy(false, StatusText.Text);
        }
    }

    private async void StopButton_Click(object sender, RoutedEventArgs e)
    {
        if (_sshClient is null)
        {
            return;
        }

        SetBusy(true, "正在停止远程服务...");
        try
        {
            _tunnel?.Dispose();
            _tunnel = null;
            _dashboardUrl = null;
            AppendActivity((await _deploymentService.StopAsync(_sshClient)).Trim());
            SetConnectedControls(false);
            ConnectionBadge.Text = "SSH 已连接";
            SetStatus("远程服务已停止");
        }
        catch (Exception exception)
        {
            AppendActivity(exception.Message);
            SetStatus("停止失败");
        }
        finally
        {
            SetBusy(false, StatusText.Text);
        }
    }

    private async void LogsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_sshClient is null)
        {
            return;
        }

        SetBusy(true, "正在读取服务日志...");
        try
        {
            AppendActivity(await _deploymentService.LogsAsync(_sshClient));
            SetStatus("日志已更新");
        }
        catch (Exception exception)
        {
            AppendActivity(exception.Message);
            SetStatus("日志读取失败");
        }
        finally
        {
            SetBusy(false, StatusText.Text);
        }
    }

    private void OpenButton_Click(object sender, RoutedEventArgs e) => OpenDashboard();

    private void BrowsePrivateKey_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "选择 SSH 私钥",
            Filter = "SSH 私钥|id_*;*.pem;*.key|所有文件|*.*",
            CheckFileExists = true,
        };
        if (dialog.ShowDialog(this) == true)
        {
            _privateKeyPath = dialog.FileName;
            UpdatePrivateKeyDisplay();
        }
    }

    private ConnectionOptions ReadOptions()
    {
        if (!int.TryParse(PortTextBox.Text.Trim(), out var port))
        {
            throw new ArgumentException("SSH 端口必须是数字。");
        }

        var fingerprint = string.Equals(HostTextBox.Text.Trim(), _settings.Host, StringComparison.OrdinalIgnoreCase)
            ? _settings.TrustedHostFingerprint
            : string.Empty;
        return new ConnectionOptions(
            HostTextBox.Text.Trim(),
            port,
            UsernameTextBox.Text.Trim(),
            _privateKeyPath,
            string.Empty,
            fingerprint);
    }

    private string? PromptSecret(string prompt)
    {
        var preenteredCode = Interlocked.Exchange(ref _pendingVerificationCode, null);
        if (!string.IsNullOrWhiteSpace(preenteredCode))
        {
            AppendActivity("已使用预输入动态验证码。下次认证如再次要求验证码，将弹出输入框。");
            return preenteredCode;
        }

        var remaining = _authenticationDeadlineUtc - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero)
        {
            AppendActivity("动态验证码等待已超时，已取消本次认证。");
            return null;
        }

        return Dispatcher.Invoke(() =>
        {
            var dialog = new SecretPromptWindow(BuildSecretPrompt(prompt), remaining) { Owner = this };
            var result = dialog.ShowDialog();
            if (dialog.TimedOut)
            {
                AppendActivity("动态验证码输入超时，已自动关闭窗口。");
            }

            return result == true ? dialog.Secret : null;
        });
    }

    private bool ConfirmHostKey(string host, string fingerprint)
    {
        return Dispatcher.Invoke(() =>
        {
            var changed = !string.IsNullOrEmpty(_settings.TrustedHostFingerprint)
                && !string.Equals(_settings.TrustedHostFingerprint, fingerprint, StringComparison.Ordinal);
            var title = changed ? "SSH 主机指纹已变化" : "确认 SSH 主机指纹";
            var message = changed
                ? $"{host} 返回的 SSH 主机指纹与之前不同。\n\n新指纹：\n{fingerprint}\n\n确认平台管理员已更换主机密钥后才能继续。"
                : $"首次连接 {host}。请通过比赛官方渠道核对主机指纹：\n\n{fingerprint}";
            var result = MessageBox.Show(
                this,
                message,
                title,
                MessageBoxButton.YesNo,
                changed ? MessageBoxImage.Warning : MessageBoxImage.Question);
            if (result != MessageBoxResult.Yes)
            {
                return false;
            }

            _acceptedFingerprint = fingerprint;
            return true;
        });
    }

    private void SaveSettings(ConnectionOptions options)
    {
        _settings = new ClientSettings
        {
            Host = options.Host,
            Port = options.Port,
            Username = options.Username,
            PrivateKeyPath = options.PrivateKeyPath,
            TrustedHostFingerprint = _acceptedFingerprint ?? options.TrustedHostFingerprint,
        };
        _settingsStore.Save(_settings);
    }

    private static string ResolvePrivateKeyPath(string configuredPath)
    {
        if (!string.IsNullOrWhiteSpace(configuredPath) && File.Exists(configuredPath))
        {
            return configuredPath;
        }

        var sshDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".ssh");
        var candidates = new[] { "id_ed25519", "id_rsa", "id_ecdsa", "id_dsa" };
        return candidates
            .Select(name => Path.Combine(sshDirectory, name))
            .FirstOrDefault(File.Exists)
            ?? string.Empty;
    }

    private void UpdatePrivateKeyDisplay()
    {
        var hasKey = !string.IsNullOrWhiteSpace(_privateKeyPath);
        PrivateKeyPathTextBlock.Text = hasKey
            ? Path.GetFileName(_privateKeyPath)
            : "未检测到 SSH 私钥，请点击右侧按钮选择";
        PrivateKeyPathTextBlock.ToolTip = hasKey ? _privateKeyPath : "自动扫描 .ssh 目录未找到私钥";
    }

    private void BeginAuthenticationStage(string stage)
    {
        _authenticationStage = stage;
        _authenticationDeadlineUtc = DateTime.UtcNow + SshConnectionService.ConnectionTimeout;
    }

    private string BuildSecretPrompt(string prompt)
    {
        var instruction = _authenticationStage == "首次安装/更新服务"
            ? "首次安装或更新服务需要第二次认证，请再次输入动态验证码。"
            : "请输入 SSH 动态验证码。";
        return string.IsNullOrWhiteSpace(prompt)
            ? instruction
            : $"{instruction}\n\n服务器提示：{prompt.Trim()}";
    }

    private string? ReadPreenteredVerificationCode()
    {
        var code = VerificationCodeTextBox.Text.Trim();
        VerificationCodeTextBox.Clear();
        return string.IsNullOrEmpty(code) ? null : code;
    }

    private void ShowRemoteState(RemoteDashboardState state)
    {
        RemoteVersionText.Text = state.Installed ? state.ReleaseId : "未安装";
        RemotePortText.Text = state.RemotePort?.ToString() ?? "-";
        AppendActivity(state.Running ? "远程服务正在运行。" : "远程服务当前未运行。");
    }

    private void OpenDashboard()
    {
        if (_dashboardUrl is not null)
        {
            Process.Start(new ProcessStartInfo(_dashboardUrl) { UseShellExecute = true });
        }
    }

    private void SetBusy(bool busy, string status)
    {
        ConnectButton.IsEnabled = !busy;
        UpdateButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        LogsButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        StopButton.IsEnabled = !busy && _tunnel is not null;
        ProgressBar.Visibility = busy ? Visibility.Visible : Visibility.Collapsed;
        ProgressBar.IsIndeterminate = busy;
        StatusText.Text = status;
    }

    private void SetConnectedControls(bool connected)
    {
        OpenButton.IsEnabled = connected;
        UpdateButton.IsEnabled = _sshClient?.IsConnected == true;
        LogsButton.IsEnabled = _sshClient?.IsConnected == true;
        StopButton.IsEnabled = connected;
    }

    private void SetStatus(string status) => Dispatcher.Invoke(() => StatusText.Text = status);

    private void AppendActivity(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return;
        }

        Dispatcher.Invoke(() =>
        {
            ActivityTextBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {message.Trim()}\n");
            ActivityTextBox.ScrollToEnd();
        });
    }

    private void Disconnect()
    {
        _tunnel?.Dispose();
        _tunnel = null;
        _dashboardUrl = null;
        if (_sshClient is not null)
        {
            if (_sshClient.IsConnected)
            {
                _sshClient.Disconnect();
            }

            _sshClient.Dispose();
            _sshClient = null;
        }

        ConnectionBadge.Text = "未连接";
        SetConnectedControls(false);
        LocalPortText.Text = "-";
    }

    private void Window_Closing(object? sender, CancelEventArgs e) => Disconnect();
}
