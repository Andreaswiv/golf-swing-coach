using Microsoft.Extensions.Options;

namespace GolfCoach.Api.Services;

/// <summary>
/// The single place that knows how files are laid out in the shared data folder.
/// Everything stored in the database or exchanged with the CV service is a path RELATIVE to this root.
/// </summary>
public sealed class StoragePaths
{
    private readonly ILogger<StoragePaths> _log;

    public string Root { get; }

    public StoragePaths(IOptions<StorageOptions> options, IHostEnvironment env, ILogger<StoragePaths> log)
        : this(Path.GetFullPath(options.Value.DataDir, env.ContentRootPath), log)
    {
    }

    // Internal so the DI container only sees the options-based constructor above; used by unit tests.
    internal StoragePaths(string absoluteRoot, ILogger<StoragePaths> log)
    {
        Root = Path.GetFullPath(absoluteRoot);
        _log = log;
    }

    public void EnsureFolders()
    {
        Directory.CreateDirectory(Path.Combine(Root, "videos"));
        Directory.CreateDirectory(Path.Combine(Root, "keypoints"));
    }

    public string VideoRelativePath(Guid videoId, string extension) => $"videos/{videoId:N}{extension.ToLowerInvariant()}";

    public string KeypointsRelativePath(Guid analysisId) => $"keypoints/{analysisId:N}.json";

    /// <summary>Resolve a relative path, refusing anything that escapes the data folder.</summary>
    public string Resolve(string relativePath)
    {
        var full = Path.GetFullPath(relativePath, Root);
        var rootWithSeparator = Root.EndsWith(Path.DirectorySeparatorChar) ? Root : Root + Path.DirectorySeparatorChar;
        if (!full.StartsWith(rootWithSeparator, StringComparison.Ordinal))
            throw new InvalidOperationException($"Path escapes the data folder: {relativePath}");
        return full;
    }

    /// <summary>Delete a file if it exists. Returns false (and logs) if deletion failed.</summary>
    public bool TryDelete(string relativePath)
    {
        try
        {
            var full = Resolve(relativePath);
            if (File.Exists(full)) File.Delete(full);
            return true;
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "Could not delete {Path}. Remove it manually from the data folder.", relativePath);
            return false;
        }
    }
}
