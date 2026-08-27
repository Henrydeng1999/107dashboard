using Renci.SshNet;

namespace Dashboard107.Client.Services;

public sealed class DashboardTunnel : IDisposable
{
    private readonly SshClient _client;
    private readonly ForwardedPortLocal _forwardedPort;

    public DashboardTunnel(SshClient client, int remotePort)
    {
        _client = client;
        _forwardedPort = new ForwardedPortLocal("127.0.0.1", "127.0.0.1", (uint)remotePort);
        _client.AddForwardedPort(_forwardedPort);
        _forwardedPort.Start();
    }

    public uint LocalPort => _forwardedPort.BoundPort;

    public string DashboardUrl => $"http://127.0.0.1:{LocalPort}/107-dashboard/";

    public void Dispose()
    {
        if (_forwardedPort.IsStarted)
        {
            _forwardedPort.Stop();
        }

        _client.RemoveForwardedPort(_forwardedPort);
        _forwardedPort.Dispose();
    }
}
