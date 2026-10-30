using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using GolfCoach.Api.Domain;

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

// Swing analysis result (cv-service/app/swing). Kept whole as JSON; these records read the parts stored as rows.
public sealed record CvSwingPhase(string Name, int FrameIndex, double TimestampS, string Method, double Confidence);

public sealed record CvSwingMeasurement(
    string Name, string? Phase, int FrameIndex, double Value, string Unit, string Type, double Confidence);

public sealed record CvSwing(string Version, string Status, List<CvSwingPhase> Phases, List<CvSwingMeasurement> Measurements);

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

public sealed class CvServiceClient(HttpClient http) : ICvServiceClient
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    public async Task<CvJobState> SubmitJobAsync(CvJobRequest request, CancellationToken ct)
    {
        using var response = await http.PostAsJsonAsync("/jobs", request, Json, ct);
        if (!response.IsSuccessStatusCode)
            throw new CvServiceException($"CV service rejected the job ({(int)response.StatusCode}): {await response.Content.ReadAsStringAsync(ct)}");

        return await response.Content.ReadFromJsonAsync<CvJobState>(Json, ct)
               ?? throw new CvServiceException("CV service returned an empty response.");
    }

    public async Task<CvJobState?> GetJobAsync(string jobId, CancellationToken ct)
    {
        using var response = await http.GetAsync($"/jobs/{Uri.EscapeDataString(jobId)}", ct);
        if (response.StatusCode == HttpStatusCode.NotFound) return null;
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<CvJobState>(Json, ct);
    }

    public async Task<JsonElement> AnalyzeAsync(string keypointsPath, CancellationToken ct)
    {
        using var response = await http.PostAsJsonAsync("/analyze", new CvAnalyzeRequest(keypointsPath), Json, ct);
        if (!response.IsSuccessStatusCode)
            throw new CvServiceException($"CV service could not analyse the swing ({(int)response.StatusCode}): {await response.Content.ReadAsStringAsync(ct)}");
        return await response.Content.ReadFromJsonAsync<JsonElement>(Json, ct);
    }

    public async Task<CvHealth?> GetHealthAsync(CancellationToken ct)
    {
        try
        {
            using var response = await http.GetAsync("/health", ct);
            if (!response.IsSuccessStatusCode) return null;
            return await response.Content.ReadFromJsonAsync<CvHealth>(Json, ct);
        }
        catch (HttpRequestException)
        {
            return null;
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            return null; // timeout
        }
    }
}

/// <summary>The CV service answered, but refused the request (as opposed to being unreachable).</summary>
public sealed class CvServiceException(string message) : Exception(message);
