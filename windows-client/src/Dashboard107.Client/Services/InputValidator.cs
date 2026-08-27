using System.IO;
using System.Text.RegularExpressions;
using Dashboard107.Client.Models;

namespace Dashboard107.Client.Services;

public static partial class InputValidator
{
    public static void Validate(ConnectionOptions options)
    {
        if (!HostPattern().IsMatch(options.Host))
        {
            throw new ArgumentException("SSH 主机名格式不正确。");
        }

        if (options.Port is < 1 or > 65535)
        {
            throw new ArgumentException("SSH 端口必须在 1 到 65535 之间。");
        }

        if (!UsernamePattern().IsMatch(options.Username))
        {
            throw new ArgumentException("用户名只能包含小写字母、数字、点、下划线和连字符。");
        }

        if (!File.Exists(options.PrivateKeyPath))
        {
            throw new ArgumentException("请选择存在的 SSH 私钥文件。");
        }
    }

    [GeneratedRegex("^[A-Za-z0-9.-]+$")]
    private static partial Regex HostPattern();

    [GeneratedRegex("^[a-z0-9._-]+$")]
    private static partial Regex UsernamePattern();
}
