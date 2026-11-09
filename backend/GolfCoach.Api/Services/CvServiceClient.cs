using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using GolfCoach.Api.Domain;
using Microsoft.Extensions.Options;

namespace GolfCoach.Api.Services;

// These records mirror the Python service's JSON (snake_case). See cv-service/app/schemas.py and jobs.py.
public sealed record CvJobRequest(
    string AnalysisId,
    string VideoPath,
    string KeypointsPath,
    string CameraAngle,
    string Handedness);

public sealed record CvVideoMeta(
    int Width,
    int Height,
    double Fps,
    int DeclaredFrameCount,
    double DurationSeconds,
    string Orientation,
    int RotationDegrees,
    string Codec);

public sealed record CvKeypointsInfo(string Path, int FrameCount, string DataFormat);

public sealed record CvResult(
    string PipelineVersion,
    string PoseModel,
    CvVideoMeta Video,
    CvKeypointsInfo Keypoints,
    JsonElement Quality,
    JsonElement? Swing);

public sealed record CvAnalyzeRequest(string KeypointsPath);

public sealed record CvJobState(
    string JobId,
    string AnalysisId,
    string Status,
    int Progress,
    string Stage,
    string? Error,
    CvResult? Result);

public sealed record CvHealth(string Status, string PipelineVersion, bool PoseModelPresent, bool DataDirPresent);

public interface ICvServiceClient
{
    Task<CvJobState> SubmitJobAsync(CvJobRequest request, CancellationToken ct);

    /// <summary>Returns null if the CV service does not know the job (it restarted and lost its in-memory state).</summary>
    Task<CvJobState?> GetJobAsync(string jobId, CancellationToken ct);

    Task<CvHealth?> GetHealthAsync(CancellationToken ct);

    /// <summary>Re-runs the swing analysis on an existing keypoints file (no pose model, takes well under a second).</summary>
    Task<JsonElement> AnalyzeAsync(string keypointsPath, CancellationToken ct);
}

/// <summary>
/// Uses the CV service running directly on this machine when it is healthy (inference can be several
/// times faster than in Docker's VM), otherwise the one in Docker. One instance follows one analysis:
/// polling goes to the service that got the job.
/// </summary>
public sealed class CvServiceClient(HttpClient http, IOptions<CvServiceOptions> options) : ICvServiceClient
{
    private static readonly TimeSpan NativeProbeLimit = TimeSpan.FromSeconds(3);
    private static readonly TimeSpan DockerProbeLimit = TimeSpan.FromSeconds(30);

    private readonly Uri _docker = new(options.Value.BaseUrl);
    private readonly Uri? _native = string.IsNullOrWhiteSpace(options.Value.NativeUrl) ? null : new(options.Value.NativeUrl);
    private Uri? _jobHost;

    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    public async Task<CvJobState> SubmitJobAsync(CvJobRequest request, CancellationToken ct)
    {
        _jobHost = await ChooseHostAsync(ct);
        using var response = await http.PostAsJsonAsync(new Uri(_jobHost, "/jobs"), request, Json, ct);
        if (!response.IsSuccessStatusCode)
            throw new CvServiceException($"CV service rejected the job ({(int)response.StatusCode}): {await response.Content.ReadAsStringAsync(ct)}");

        return await response.Content.ReadFromJsonAsync<CvJobState>(Json, ct)
               ?? throw new CvServiceException("CV service returned an empty response.");
    }

    public async Task<CvJobState?> GetJobAsync(string jobId, CancellationToken ct)
    {
        var host = _jobHost ?? _docker;
        HttpResponseMessage sent;
        try
        {
            sent = await http.GetAsync(new Uri(host, $"/jobs/{Uri.EscapeDataString(jobId)}"), ct);
        }
        catch (HttpRequestException) when (host == _native)
        {
            return null; // the native service went away: the worker resubmits, which falls back to Docker
        }

        using var response = sent;
        if (response.StatusCode == HttpStatusCode.NotFound) return null;
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<CvJobState>(Json, ct);
    }

    public async Task<JsonElement> AnalyzeAsync(string keypointsPath, CancellationToken ct)
    {
        var host = await ChooseHostAsync(ct);
        using var response = await http.PostAsJsonAsync(new Uri(host, "/analyze"), new CvAnalyzeRequest(keypointsPath), Json, ct);
        if (!response.IsSuccessStatusCode)
            throw new CvServiceException($"CV service could not analyse the swing ({(int)response.StatusCode}): {await response.Content.ReadAsStringAsync(ct)}");
        return await response.Content.ReadFromJsonAsync<JsonElement>(Json, ct);
    }

    public async Task<CvHealth?> GetHealthAsync(CancellationToken ct) =>
        await HealthyNativeAsync(ct) ?? await HealthAsync(_docker, DockerProbeLimit, ct);

    private async Task<Uri> ChooseHostAsync(CancellationToken ct) =>
        await HealthyNativeAsync(ct) is null ? _docker : _native!;

    private async Task<CvHealth?> HealthyNativeAsync(CancellationToken ct)
    {
        if (_native is null) return null;
        var health = await HealthAsync(_native, NativeProbeLimit, ct);
        return health is { Status: "ok" } ? health : null;
    }

    private async Task<CvHealth?> HealthAsync(Uri host, TimeSpan limit, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(limit);
        try
        {
            using var response = await http.GetAsync(new Uri(host, "/health"), timeout.Token);
            if (!response.IsSuccessStatusCode) return null;
            return await response.Content.ReadFromJsonAsync<CvHealth>(Json, timeout.Token);
        }
        catch (HttpRequestException)
        {
            return null;
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return null; // timeout
        }
    }
}

/// <summary>The CV service answered, but refused the request (as opposed to being unreachable).</summary>
public sealed class CvServiceException(string message) : Exception(message);
