namespace Dashboard107.Client.Models;

public sealed class DeploymentCache
{
    public string Host { get; set; } = string.Empty;

    public int Port { get; set; }

    public string Username { get; set; } = string.Empty;

    public string ReleaseId { get; set; } = string.Empty;

    public int RemotePort { get; set; }

    public DateTimeOffset LastValidatedUtc { get; set; }
}
