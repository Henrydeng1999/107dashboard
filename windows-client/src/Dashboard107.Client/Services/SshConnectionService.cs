using Dashboard107.Client.Models;
using Renci.SshNet;

namespace Dashboard107.Client.Services;

public sealed class SshConnectionService
{
    internal static readonly TimeSpan ConnectionTimeout = TimeSpan.FromSeconds(60);

    public async Task<SshClient> ConnectSshAsync(
        ConnectionOptions options,
        Func<string, string?> promptSecret,
        Func<string, string, bool> confirmHostKey,
        CancellationToken cancellationToken = default)
    {
        InputValidator.Validate(options);
        var client = new SshClient(CreateConnectionInfo(options, promptSecret));
        ConfigureClient(client, options, confirmHostKey);
        try
        {
            await Task.Run(client.Connect, cancellationToken);
            return client;
        }
        catch
        {
            client.Dispose();
            throw;
        }
    }

    public async Task<SftpClient> ConnectSftpAsync(
        ConnectionOptions options,
        Func<string, string?> promptSecret,
        Func<string, string, bool> confirmHostKey,
        CancellationToken cancellationToken = default)
    {
        InputValidator.Validate(options);
        var client = new SftpClient(CreateConnectionInfo(options, promptSecret));
        ConfigureClient(client, options, confirmHostKey);
        try
        {
            await Task.Run(client.Connect, cancellationToken);
            return client;
        }
        catch
        {
            client.Dispose();
            throw;
        }
    }

    private static ConnectionInfo CreateConnectionInfo(
        ConnectionOptions options,
        Func<string, string?> promptSecret)
    {
        var privateKey = string.IsNullOrEmpty(options.PrivateKeyPassphrase)
            ? new PrivateKeyFile(options.PrivateKeyPath)
            : new PrivateKeyFile(options.PrivateKeyPath, options.PrivateKeyPassphrase);
        var publicKey = new PrivateKeyAuthenticationMethod(options.Username, privateKey);
        var interactive = new KeyboardInteractiveAuthenticationMethod(options.Username);
        interactive.AuthenticationPrompt += (_, eventArgs) =>
        {
            foreach (var prompt in eventArgs.Prompts)
            {
                prompt.Response = promptSecret(prompt.Request)
                    ?? throw new OperationCanceledException("已取消动态验证码输入。");
            }
        };
        return new ConnectionInfo(
            options.Host,
            options.Port,
            options.Username,
            publicKey,
            interactive)
        {
            Timeout = ConnectionTimeout,
        };
    }

    private static void ConfigureClient(
        BaseClient client,
        ConnectionOptions options,
        Func<string, string, bool> confirmHostKey)
    {
        client.KeepAliveInterval = TimeSpan.FromSeconds(15);
        client.HostKeyReceived += (_, eventArgs) =>
        {
            var fingerprint = eventArgs.FingerPrintSHA256;
            eventArgs.CanTrust = string.Equals(
                    fingerprint,
                    options.TrustedHostFingerprint,
                    StringComparison.Ordinal)
                || confirmHostKey(options.Host, fingerprint);
        };
    }
}
