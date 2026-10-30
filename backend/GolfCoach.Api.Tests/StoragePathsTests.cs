using GolfCoach.Api.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace GolfCoach.Api.Tests;

public class StoragePathsTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "golfcoach-tests-" + Guid.NewGuid().ToString("N"));
    private readonly StoragePaths _paths;

    public StoragePathsTests()
    {
        Directory.CreateDirectory(_root);
        _paths = new StoragePaths(_root, NullLogger<StoragePaths>.Instance);
    }

    public void Dispose() => Directory.Delete(_root, recursive: true);

    [Fact]
    public void Builds_relative_paths_from_ids()
    {
        var id = Guid.Parse("11111111-2222-3333-4444-555555555555");
        Assert.Equal("videos/11111111222233334444555555555555.mp4", _paths.VideoRelativePath(id, ".MP4"));
        Assert.Equal("keypoints/11111111222233334444555555555555.json", _paths.KeypointsRelativePath(id));
    }

    [Fact]
    public void Resolve_stays_inside_the_data_folder()
    {
        Assert.StartsWith(_paths.Root, _paths.Resolve("videos/a.mp4"));
        Assert.Throws<InvalidOperationException>(() => _paths.Resolve("../outside.mp4"));
        Assert.Throws<InvalidOperationException>(() => _paths.Resolve("videos/../../outside.mp4"));
    }

    [Fact]
    public void TryDelete_removes_files_and_tolerates_missing_ones()
    {
        _paths.EnsureFolders();
        var file = _paths.Resolve("keypoints/x.json");
        File.WriteAllText(file, "{}");

        Assert.True(_paths.TryDelete("keypoints/x.json"));
        Assert.False(File.Exists(file));
        Assert.True(_paths.TryDelete("keypoints/does-not-exist.json"));
        Assert.False(_paths.TryDelete("../../etc/passwd"));
    }
}
