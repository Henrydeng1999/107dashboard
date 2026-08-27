using System.Windows;
using System.Windows.Input;

namespace Dashboard107.Client;

public partial class SecretPromptWindow : Window
{
    public SecretPromptWindow(string prompt)
    {
        InitializeComponent();
        PromptText.Text = string.IsNullOrWhiteSpace(prompt) ? "请输入动态验证码" : prompt.Trim();
        Loaded += (_, _) => SecretBox.Focus();
    }

    public string Secret => SecretBox.Password;

    private void Confirm_Click(object sender, RoutedEventArgs e) => DialogResult = true;

    private void SecretBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            DialogResult = true;
        }
    }
}
