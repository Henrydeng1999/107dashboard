namespace Dashboard107.Client.Models;

public sealed class ClientSettings
{
    public string Host { get; set; } = "107.ustc.edu.cn";

    public int Port { get; set; } = 22;

    public string Username { get; set; } = string.Empty;

    public string PrivateKeyPath { get; set; } = string.Empty;

    public string TrustedHostFingerprint { get; set; } = string.Empty;
}
