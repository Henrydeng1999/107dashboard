namespace Dashboard107.Client.Services;

public static class ShellQuote
{
    public static string Posix(string value) => $"'{value.Replace("'", "'\"'\"'")}'";
}
