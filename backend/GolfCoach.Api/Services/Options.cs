namespace GolfCoach.Api.Services;

public sealed class StorageOptions
{
    /// <summary>Folder shared with the CV service. Relative paths resolve against the content root.</summary>
    public string DataDir { get; set; } = "../../data";
}

public sealed class CvServiceOptions
{
    /// <summary>The CV service in Docker: always there, used when the native one is not.</summary>
    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>The CV service running directly on this machine (scripts/native_cv.py), used first. Empty = none.</summary>
    public string? NativeUrl { get; set; }
}

public sealed class UploadOptions
{
    public int MaxMegabytes { get; set; } = 500;
    public long MaxBytes => MaxMegabytes * 1024L * 1024L;
}
