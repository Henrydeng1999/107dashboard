using System.IO;
using System.Text.Json;
using Dashboard107.Client.Models;

namespace Dashboard107.Client.Services;

public sealed class DeploymentCacheStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly string _cachePath;

    public DeploymentCacheStore(string? applicationDirectory = null)
    {
        var directory = Path.Combine(applicationDirectory ?? AppContext.BaseDirectory, "data");
        Directory.CreateDirectory(directory);
        _cachePath = Path.Combine(directory, "deployment-cache.json");
    }

    public bool TryLoad(
        ConnectionOptions options,
        string releaseId,
        out DeploymentCache? cache)
    {
        cache = null;
        if (!File.Exists(_cachePath))
        {
            return false;
        }

        try
        {
            cache = JsonSerializer.Deserialize<DeploymentCache>(File.ReadAllText(_cachePath));
        }
        catch (JsonException)
        {
            return false;
        }
        catch (IOException)
        {
            return false;
        }
        catch (UnauthorizedAccessException)
        {
            return false;
        }

        if (cache is null
            || !string.Equals(cache.Host, options.Host, StringComparison.OrdinalIgnoreCase)
            || cache.Port != options.Port
            || !string.Equals(cache.Username, options.Username, StringComparison.Ordinal)
            || !string.Equals(cache.ReleaseId, releaseId, StringComparison.Ordinal)
            || cache.RemotePort is < 1 or > 65535)
        {
            cache = null;
            return false;
        }

        return true;
    }

    public void Save(DeploymentCache cache)
    {
        if (cache.RemotePort is < 1 or > 65535)
        {
            throw new ArgumentOutOfRangeException(nameof(cache), "远程服务端口必须在 1 到 65535 之间。");
        }

        var temporaryPath = _cachePath + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(cache, JsonOptions));
        File.Move(temporaryPath, _cachePath, true);
    }

    public void Clear()
    {
        try
        {
            File.Delete(_cachePath);
        }
        catch (FileNotFoundException)
        {
            // The cache was already absent.
        }
        catch (DirectoryNotFoundException)
        {
            // The portable data directory was removed with the cache.
        }
        catch (IOException)
        {
            // A stale cache must never block the full connection path.
        }
        catch (UnauthorizedAccessException)
        {
            // A stale cache must never block the full connection path.
        }
    }
}
