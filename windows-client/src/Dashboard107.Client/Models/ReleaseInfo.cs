namespace Dashboard107.Client.Models;

public sealed record ReleaseInfo(
    string Version,
    string Commit,
    string ReleaseId,
    string ArchiveRoot,
    string Sha256);
