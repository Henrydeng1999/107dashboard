using System.ComponentModel;
using System.Drawing;
using System.IO;
using System.Windows;
using Dashboard107.Client.Models;
using Dashboard107.Client.Services;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Microsoft.Win32;
using Renci.SshNet;
using Renci.SshNet.Common;
using DrawingIcon = System.Drawing.Icon;
using Forms = System.Windows.Forms;

namespace Dashboard107.Client;

public partial class MainWindow : Window
{
    private readonly SettingsStore _settingsStore = new();
    private readonly DeploymentCacheStore _deploymentCacheStore = new();
    private readonly SshConnectionService _connectionService = new();
    private readonly RemoteDeploymentService _deploymentService = new();
    private readonly Lazy<ReleasePackage> _embeddedPackage = new(ReleasePackage.LoadEmbedded);
    private ClientSettings _settings;
    private string _privateKeyPath = string.Empty;
    private SshClient? _sshClient;
    private DashboardTunnel? _tunnel;
    private string? _dashboardUrl;
    private string? _acceptedFingerprint;
    private string? _pendingVerificationCode;
    private string? _verificationCodeForReuse;
    private string? _authenticationStage;
    private DateTime _authenticationDeadlineUtc;
    private CancellationTokenSource? _operationCancellation;
    private readonly string _webViewUserDataDirectory = Path.Combine(
        AppContext.BaseDirectory,
        "data",
        "webview2");
    private Forms.NotifyIcon? _trayIcon;
    private Forms.ContextMenuStrip? _trayMenu;
    private DrawingIcon? _trayIconImage;
    private Stream? _trayIconResourceStream;
    private bool _isClosing;

    public MainWindow()
    {
        InitializeComponent();
        InitializeTrayIcon();
        DashboardWebView.NavigationCompleted += DashboardWebView_NavigationCompleted;
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
        var operationCancellation = new CancellationTokenSource();
        _operationCancellation = operationCancellation;
        var cancellationToken = operationCancellation.Token;
        _pendingVerificationCode = ReadPreenteredVerificationCode();
        _verificationCodeForReuse = _pendingVerificationCode;
        ShowConnectionView();
        BeginAuthenticationStage("SSH 主连接");
        SetBusy(true, "正在连接 SSH...");
        try
        {
            Disconnect();
            var options = ReadOptions();
            var package = _embeddedPackage.Value;
            DeploymentCache? cachedDeployment = null;
            var hasDeploymentCache = !forceDeployment
                && _deploymentCacheStore.TryLoad(
                    options,
                    package.Info.ReleaseId,
                    out cachedDeployment);
            _acceptedFingerprint = null;
            _sshClient = await _connectionService.ConnectSshAsync(
                options,
                PromptSecret,
                ConfirmHostKey,
                cancellationToken);
            SaveSettings(options);
            ConnectionBadge.Text = "SSH 已连接";
            AppendActivity($"已连接 {options.Username}@{options.Host}:{options.Port}");

            int remotePort;
            if (hasDeploymentCache && cachedDeployment is not null)
            {
                try
                {
                    SetStatus("正在快速启动远程服务...");
                    RemoteVersionText.Text = package.Info.ReleaseId;
                    RemotePortText.Text = cachedDeployment.RemotePort.ToString();
                    AppendActivity("已命中本地部署缓存，跳过平台环境检查和版本扫描。");
                    remotePort = await _deploymentService.EnsureStartedAsync(
                        _sshClient,
                        cancellationToken);
                    SaveDeploymentCache(options, package, remotePort);
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    _deploymentCacheStore.Clear();
                    AppendActivity($"本地部署缓存校验失败，将执行完整检查：{exception.Message}");
                    remotePort = await PrepareRemoteServiceAsync(
                        options,
                        package,
                        forceDeployment: false,
                        cancellationToken);
                }
            }
            else
            {
                if (!forceDeployment)
                {
                    AppendActivity("未找到当前平台和服务版本的部署缓存，将执行首次完整检查。");
                }

                remotePort = await PrepareRemoteServiceAsync(
                    options,
                    package,
                    forceDeployment,
                    cancellationToken);
            }

            _tunnel = new DashboardTunnel(_sshClient, remotePort);
            _dashboardUrl = _tunnel.DashboardUrl;
            RemotePortText.Text = remotePort.ToString();
            LocalPortText.Text = _tunnel.LocalPort.ToString();
            ConnectionBadge.Text = "平台可用";
            AppendActivity($"本地入口 {_dashboardUrl}");
            SetConnectedControls(true);
            await OpenDashboardAsync();
            SetStatus("平台已连接");
        }
        catch (OperationCanceledException)
        {
            if (_isClosing)
            {
                return;
            }

            AppendActivity("操作已取消。");
            SetStatus("已取消");
            if (_sshClient?.IsConnected != true || _tunnel is null)
            {
                Disconnect();
            }
            else
            {
                ConnectionBadge.Text = "平台可用";
                SetConnectedControls(true);
            }
        }
        catch (Exception exception)
        {
            if (_isClosing)
            {
                return;
            }

            AppendActivity(exception.Message);
            SetStatus("连接失败");
            System.Windows.MessageBox.Show(this, exception.Message, "107 Dashboard", MessageBoxButton.OK, MessageBoxImage.Error);
            Disconnect();
        }
        finally
        {
            _pendingVerificationCode = null;
            _verificationCodeForReuse = null;
            _authenticationStage = null;
            if (ReferenceEquals(_operationCancellation, operationCancellation))
            {
                _operationCancellation = null;
            }

            operationCancellation.Dispose();
            if (!_isClosing)
            {
                SetBusy(false, StatusText.Text);
            }
        }
    }

    private async void StopButton_Click(object sender, RoutedEventArgs e) =>
        await StopRemoteServiceAsync();

    private async Task StopRemoteServiceAsync()
    {
        if (_sshClient is null)
        {
            return;
        }

        SetBusy(true, "正在停止远程服务...");
        try
        {
            AppendActivity((await _deploymentService.StopAsync(_sshClient)).Trim());
            Disconnect();
            ShowConnectionView();
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

    private async void LogsButton_Click(object sender, RoutedEventArgs e) =>
        await ShowRemoteLogsAsync();

    private async Task ShowRemoteLogsAsync()
    {
        if (_sshClient is null)
        {
            return;
        }

        SetBusy(true, "正在读取服务日志...");
        try
        {
            var logs = await _deploymentService.LogsAsync(_sshClient);
            AppendActivity(logs);
            ShowLogWindow(logs);
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

    private async void OpenButton_Click(object sender, RoutedEventArgs e) =>
        await OpenDashboardAsync();

    private void ConnectionSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        ShowConnectionView();
        SetStatus(_tunnel is null
            ? "已打开连接设置"
            : "已打开连接设置，当前隧道仍保持连接；点击“进入主界面”可返回平台");
    }

    private void MinimizeToTrayButton_Click(object sender, RoutedEventArgs e) => HideToTray();

    private void BrowsePrivateKey_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
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
            _verificationCodeForReuse = preenteredCode;
            AppendActivity("已使用本次动态验证码。");
            return preenteredCode;
        }

        var remaining = _authenticationDeadlineUtc - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero)
        {
            AppendActivity("动态验证码等待已超时，已取消本次认证。");
            return null;
        }

        var secret = Dispatcher.Invoke(() =>
        {
            var dialog = new SecretPromptWindow(BuildSecretPrompt(prompt), remaining) { Owner = this };
            var result = dialog.ShowDialog();
            if (dialog.TimedOut)
            {
                AppendActivity("动态验证码输入超时，已自动关闭窗口。");
            }

            return result == true ? dialog.Secret : null;
        });
        if (!string.IsNullOrWhiteSpace(secret))
        {
            _verificationCodeForReuse = secret;
        }

        return secret;
    }

    private async Task<SftpClient> ConnectSftpWithCodeReuseAsync(
        ConnectionOptions options,
        CancellationToken cancellationToken)
    {
        var sftpOptions = options with { TrustedHostFingerprint = _settings.TrustedHostFingerprint };
        var reusedCode = _verificationCodeForReuse;
        var shouldRetryWithPrompt = !string.IsNullOrWhiteSpace(reusedCode);
        if (shouldRetryWithPrompt)
        {
            _pendingVerificationCode = reusedCode;
            AppendActivity("正在尝试复用本次 SSH 认证的动态验证码连接 SFTP。");
        }

        try
        {
            return await _connectionService.ConnectSftpAsync(
                sftpOptions,
                PromptSecret,
                ConfirmHostKey,
                cancellationToken);
        }
        catch (SshAuthenticationException) when (shouldRetryWithPrompt)
        {
            _pendingVerificationCode = null;
            AppendActivity("本次验证码无法复用，正在请求输入新的动态验证码。");
            return await _connectionService.ConnectSftpAsync(
                sftpOptions,
                PromptSecret,
                ConfirmHostKey,
                cancellationToken);
        }
        finally
        {
            _pendingVerificationCode = null;
        }
    }

    private async Task<int> PrepareRemoteServiceAsync(
        ConnectionOptions options,
        ReleasePackage package,
        bool forceDeployment,
        CancellationToken cancellationToken)
    {
        SetStatus("正在检查平台环境...");
        AppendActivity((await _deploymentService.CheckEnvironmentAsync(_sshClient!, cancellationToken)).Trim());

        var state = await _deploymentService.GetStateAsync(_sshClient!, cancellationToken);
        ShowRemoteState(state);
        var needsDeployment = forceDeployment
            || !state.Installed
            || !string.Equals(state.ReleaseId, package.Info.ReleaseId, StringComparison.Ordinal);

        if (needsDeployment)
        {
            SetStatus("正在验证文件传输连接...");
            AppendActivity($"准备部署服务端 {package.Info.ReleaseId}");
            BeginAuthenticationStage("首次安装/更新服务");
            AppendActivity("首次安装或更新需要 SFTP 认证，将先复用本次验证码；若服务器拒绝，再弹窗输入新的验证码。");
            using var sftp = await ConnectSftpWithCodeReuseAsync(options, cancellationToken);
            var progress = new Progress<double>(value =>
            {
                ProgressBar.IsIndeterminate = false;
                ProgressBar.Value = value * 100;
                StatusText.Text = $"正在上传服务包 {value:P0}";
            });
            var deploymentOutput = new Progress<string>(line =>
            {
                AppendActivity($"远程：{line}");
                if (line == "服务包已上传，开始校验并安装。")
                {
                    ProgressBar.IsIndeterminate = true;
                    StatusText.Text = "正在安装远程服务...";
                }
            });
            await _deploymentService.DeployAsync(
                _sshClient!,
                sftp,
                package,
                progress,
                deploymentOutput,
                cancellationToken: cancellationToken);
            state = await _deploymentService.GetStateAsync(_sshClient!, cancellationToken);
            ShowRemoteState(state);
        }

        SetStatus("正在启动远程服务...");
        var remotePort = await _deploymentService.EnsureStartedAsync(_sshClient!, cancellationToken);
        SaveDeploymentCache(options, package, remotePort);
        return remotePort;
    }

    private void SaveDeploymentCache(
        ConnectionOptions options,
        ReleasePackage package,
        int remotePort)
    {
        try
        {
            _deploymentCacheStore.Save(new DeploymentCache
            {
                Host = options.Host,
                Port = options.Port,
                Username = options.Username,
                ReleaseId = package.Info.ReleaseId,
                RemotePort = remotePort,
                LastValidatedUtc = DateTimeOffset.UtcNow,
            });
        }
        catch (IOException exception)
        {
            AppendActivity($"部署缓存写入失败，下次连接将执行完整检查：{exception.Message}");
        }
        catch (UnauthorizedAccessException exception)
        {
            AppendActivity($"部署缓存写入失败，下次连接将执行完整检查：{exception.Message}");
        }
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
            var result = System.Windows.MessageBox.Show(
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

    private async Task OpenDashboardAsync()
    {
        if (string.IsNullOrWhiteSpace(_dashboardUrl))
        {
            return;
        }

        ConnectionView.Visibility = Visibility.Collapsed;
        DashboardView.Visibility = Visibility.Visible;
        WebViewErrorPanel.Visibility = Visibility.Collapsed;
        try
        {
            Directory.CreateDirectory(_webViewUserDataDirectory);
            if (DashboardWebView.CoreWebView2 is null)
            {
                DashboardWebView.CreationProperties = new CoreWebView2CreationProperties
                {
                    UserDataFolder = _webViewUserDataDirectory,
                };
                await DashboardWebView.EnsureCoreWebView2Async();
            }

            var webView = DashboardWebView.CoreWebView2
                ?? throw new InvalidOperationException("WebView2 初始化后仍未提供核心对象。");
            webView.Navigate(_dashboardUrl);
            DashboardWebView.Focus();
        }
        catch (Exception exception)
        {
            WebViewErrorText.Text =
                "请确认系统已安装 Microsoft Edge WebView2 Runtime，然后重试。\n\n"
                + exception.Message;
            WebViewErrorPanel.Visibility = Visibility.Visible;
            AppendActivity($"内置主界面加载失败：{exception.Message}");
        }
    }

    private void SetBusy(bool busy, string status)
    {
        ConnectButton.IsEnabled = !busy;
        UpdateButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        LogsButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        StopButton.IsEnabled = !busy && _tunnel is not null;
        DashboardUpdateButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        DashboardLogsButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        DashboardConnectionButton.IsEnabled = !busy && _sshClient?.IsConnected == true;
        DashboardStopButton.IsEnabled = !busy && _tunnel is not null;
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
        DashboardUpdateButton.IsEnabled = connected;
        DashboardLogsButton.IsEnabled = connected;
        DashboardConnectionButton.IsEnabled = connected;
        DashboardStopButton.IsEnabled = connected;
        _trayIcon!.Text = connected ? "107 Dashboard - 平台已连接" : "107 Dashboard - 未连接";
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
        if (DashboardWebView.CoreWebView2 is not null)
        {
            DashboardWebView.CoreWebView2.Stop();
        }
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

    private void ShowConnectionView()
    {
        DashboardView.Visibility = Visibility.Collapsed;
        ConnectionView.Visibility = Visibility.Visible;
        WebViewErrorPanel.Visibility = Visibility.Collapsed;
    }

    private void ShowLogWindow(string logs)
    {
        var logWindow = new Window
        {
            Owner = this,
            Title = "107 Dashboard 服务日志",
            Width = 920,
            Height = 580,
            MinWidth = 640,
            MinHeight = 360,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
        };
        logWindow.Content = new System.Windows.Controls.TextBox
        {
            Text = logs,
            IsReadOnly = true,
            AcceptsReturn = true,
            TextWrapping = TextWrapping.NoWrap,
            VerticalScrollBarVisibility = System.Windows.Controls.ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = System.Windows.Controls.ScrollBarVisibility.Auto,
            Padding = new Thickness(14),
            FontFamily = new System.Windows.Media.FontFamily("Cascadia Mono"),
        };
        logWindow.Show();
    }

    private void InitializeTrayIcon()
    {
        _trayMenu = new Forms.ContextMenuStrip();
        var showItem = new Forms.ToolStripMenuItem("显示主界面");
        showItem.Click += (_, _) => ShowFromTray();
        var openItem = new Forms.ToolStripMenuItem("打开平台");
        openItem.Click += (_, _) => ShowFromTray();
        var logsItem = new Forms.ToolStripMenuItem("查看服务日志");
        logsItem.Click += async (_, _) => await ShowRemoteLogsAsync();
        var stopItem = new Forms.ToolStripMenuItem("停止远程服务");
        stopItem.Click += async (_, _) => await StopRemoteServiceAsync();
        var exitItem = new Forms.ToolStripMenuItem("退出");
        exitItem.Click += (_, _) => ExitApplication();
        _trayMenu.Items.Add(showItem);
        _trayMenu.Items.Add(openItem);
        _trayMenu.Items.Add(logsItem);
        _trayMenu.Items.Add(new Forms.ToolStripSeparator());
        _trayMenu.Items.Add(stopItem);
        _trayMenu.Items.Add(new Forms.ToolStripSeparator());
        _trayMenu.Items.Add(exitItem);

        DrawingIcon? icon = null;
        try
        {
            var resource = System.Windows.Application.GetResourceStream(
                new Uri("pack://application:,,,/Assets/107dashboard.ico"));
            if (resource is not null)
            {
                _trayIconResourceStream = resource.Stream;
                _trayIconImage = new DrawingIcon(_trayIconResourceStream);
                icon = _trayIconImage;
            }
        }
        catch (Exception exception)
        {
            AppendActivity($"托盘图标加载失败，将使用系统图标：{exception.Message}");
        }

        _trayIcon = new Forms.NotifyIcon
        {
            Icon = icon ?? SystemIcons.Application,
            Text = "107 Dashboard - 未连接",
            ContextMenuStrip = _trayMenu,
            Visible = true,
        };
        _trayIcon.DoubleClick += (_, _) => ShowFromTray();
    }

    private void ShowFromTray()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }

    private void HideToTray()
    {
        if (_isClosing || !IsVisible)
        {
            return;
        }

        WindowState = WindowState.Normal;
        Hide();
        _trayIcon?.ShowBalloonTip(
            1200,
            "107 Dashboard",
            "客户端已最小化到系统托盘。",
            Forms.ToolTipIcon.Info);
    }

    private void ExitApplication()
    {
        _isClosing = true;
        Close();
    }

    private void DashboardWebView_NavigationCompleted(
        object? sender,
        CoreWebView2NavigationCompletedEventArgs eventArgs)
    {
        if (eventArgs.IsSuccess)
        {
            WebViewErrorPanel.Visibility = Visibility.Collapsed;
            return;
        }

        WebViewErrorText.Text = $"页面请求失败：{eventArgs.WebErrorStatus}";
        WebViewErrorPanel.Visibility = Visibility.Visible;
        AppendActivity($"主界面页面请求失败：{eventArgs.WebErrorStatus}");
    }

    private void Window_StateChanged(object? sender, EventArgs e)
    {
        if (WindowState == WindowState.Minimized && !_isClosing)
        {
            Dispatcher.BeginInvoke(HideToTray);
        }
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        _isClosing = true;
        _operationCancellation?.Cancel();
        Disconnect();
        if (_trayIcon is not null)
        {
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
            _trayIcon = null;
        }
        _trayMenu?.Dispose();
        _trayMenu = null;
        _trayIconImage?.Dispose();
        _trayIconImage = null;
        _trayIconResourceStream?.Dispose();
        _trayIconResourceStream = null;
    }

    private void Window_Closed(object? sender, EventArgs e)
    {
        System.Windows.Application.Current.Shutdown();
    }
}
