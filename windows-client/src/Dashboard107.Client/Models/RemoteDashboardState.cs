namespace Dashboard107.Client.Models;

public sealed record RemoteDashboardState(
    bool Installed,
    bool Running,
    string ReleaseId,
    int? RemotePort,
    string Details);
