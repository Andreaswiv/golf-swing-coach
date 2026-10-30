namespace GolfCoach.Api.Services;

public sealed class StorageOptions
{
    /// <summary>Folder shared with the CV service. Relative paths resolve against the content root.</summary>
    public string DataDir { get; set; } = "../../data";
}

public sealed class CvServiceOptions
{
    public string BaseUrl { get; set; } = "http://localhost:8000";
}

public sealed class UploadOptions
{
    public int MaxMegabytes { get; set; } = 500;
    public long MaxBytes => MaxMegabytes * 1024L * 1024L;
}
