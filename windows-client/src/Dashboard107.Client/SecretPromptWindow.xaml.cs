using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;

namespace Dashboard107.Client;

public partial class SecretPromptWindow : Window
{
    private readonly DateTime _deadlineUtc;
    private readonly DispatcherTimer _timeoutTimer = new() { Interval = TimeSpan.FromSeconds(1) };

    public SecretPromptWindow(string prompt)
        : this(prompt, TimeSpan.FromSeconds(60))
    {
    }

    public SecretPromptWindow(string prompt, TimeSpan timeout)
    {
        InitializeComponent();
        PromptText.Text = string.IsNullOrWhiteSpace(prompt) ? "请输入动态验证码" : prompt.Trim();
        _deadlineUtc = DateTime.UtcNow + timeout;
        _timeoutTimer.Tick += TimeoutTimer_Tick;
        Loaded += SecretPromptWindow_Loaded;
        Closed += (_, _) => _timeoutTimer.Stop();
    }

    public string Secret => SecretBox.Password;

    public bool TimedOut { get; private set; }

    private void Confirm_Click(object sender, RoutedEventArgs e) => DialogResult = true;

    private void SecretBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            DialogResult = true;
        }
    }

    private void SecretPromptWindow_Loaded(object sender, RoutedEventArgs e)
    {
        SecretBox.Focus();
        UpdateTimeoutText();
        _timeoutTimer.Start();
    }

    private void TimeoutTimer_Tick(object? sender, EventArgs e)
    {
        if (DateTime.UtcNow < _deadlineUtc)
        {
            UpdateTimeoutText();
            return;
        }

        TimedOut = true;
        DialogResult = false;
    }

    private void UpdateTimeoutText()
    {
        var remaining = Math.Max(0, (int)Math.Ceiling((_deadlineUtc - DateTime.UtcNow).TotalSeconds));
        TimeoutText.Text = $"验证码窗口将在 {remaining} 秒后自动关闭。";
    }
}
