namespace Dashboard107.Client.Models;

public sealed record ConnectionOptions(
    string Host,
    int Port,
    string Username,
    string PrivateKeyPath,
    string PrivateKeyPassphrase,
    string TrustedHostFingerprint);
