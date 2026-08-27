using System.Formats.Tar;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Dashboard107.Client.Models;

namespace Dashboard107.Client.Services;

public sealed partial class ReleasePackage
{
    public const string ResourceName = "Dashboard107.Client.Payload.server-package.tar.gz";
    private readonly byte[] _content;

    private ReleasePackage(byte[] content, ReleaseInfo info)
    {
        _content = content;
        Info = info;
    }

    public ReleaseInfo Info { get; }

    public static ReleasePackage LoadEmbedded()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException(
                "当前程序没有内置 Linux 服务包，请使用正式的客户端构建脚本生成 EXE。");
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return Parse(memory.ToArray());
    }

    public static ReleasePackage LoadFile(string path) => Parse(File.ReadAllBytes(path));

    public Stream OpenRead() => new MemoryStream(_content, writable: false);

    private static ReleasePackage Parse(byte[] content)
    {
        string? archiveRoot = null;
        string? version = null;
        string? commit = null;
        using var compressed = new MemoryStream(content, writable: false);
        using var gzip = new GZipStream(compressed, CompressionMode.Decompress);
        using var archive = new TarReader(gzip);
        while (archive.GetNextEntry() is { } entry)
        {
            var parts = entry.Name.Split('/', StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0)
            {
                continue;
            }

            archiveRoot ??= parts[0];
            if (!string.Equals(archiveRoot, parts[0], StringComparison.Ordinal))
            {
                throw new InvalidDataException("服务包必须只包含一个顶层目录。");
            }

            if (!entry.Name.EndsWith("/release-manifest.json", StringComparison.Ordinal)
                || entry.DataStream is null)
            {
                continue;
            }

            using var document = JsonDocument.Parse(entry.DataStream);
            version = document.RootElement.GetProperty("version").GetString();
            commit = document.RootElement.GetProperty("source_commit").GetString();
        }

        if (archiveRoot is null || version is null || commit is null || commit.Length < 8)
        {
            throw new InvalidDataException("服务包缺少有效的发布元数据。");
        }

        var checksum = Convert.ToHexString(SHA256.HashData(content)).ToLowerInvariant();
        var releaseId = $"{version}-{commit[..8]}-{checksum[..8]}";
        if (!SafeIdentifier().IsMatch(releaseId) || !SafeIdentifier().IsMatch(archiveRoot))
        {
            throw new InvalidDataException("服务包版本标识不安全。");
        }

        return new ReleasePackage(content, new ReleaseInfo(version, commit, releaseId, archiveRoot, checksum));
    }

    [GeneratedRegex("^[A-Za-z0-9._-]+$")]
    private static partial Regex SafeIdentifier();
}
