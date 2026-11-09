using System.Text.Json;
using System.Text.Json.Nodes;
using GolfCoach.Api.Domain;

namespace GolfCoach.Api.Contracts;

// JSON on the wire: property names camelCase; enums snake_case (see Program.cs).
// The "quality" and "swing" objects are passed through exactly as the CV service produced them (snake_case keys).

public sealed record VideoDto(
    Guid Id,
    string OriginalFileName,
    CameraAngle CameraAngle,
    Handedness Handedness,
    string? Club,
    int? Width,
    int? Height,
    double? Fps,
    double? DurationSeconds,
    string? Orientation,
    DateTime UploadedAt);

public sealed record KeypointsDto(int FrameCount, string DataFormat);

public sealed record AnalysisDto(
    Guid Id,
    AnalysisStatus Status,
    int Progress,
    string Stage,
    string? Error,
    DateTime CreatedAt,
    DateTime? CompletedAt,
    string? PipelineVersion,
    string? PoseModel,
    VideoDto Video,
    JsonElement? Quality,
    KeypointsDto? Keypoints,
    JsonElement? Swing);

public sealed record HealthDto(string Status, bool Database, bool CvService, bool? PoseModelPresent);

public static class DtoMapper
{
    public static AnalysisDto ToDto(Analysis a) => Build(a, ParseJson(a.SwingJson));

    /// <summary>For the list of swings: leaves out the per-frame data only the video player needs.</summary>
    public static AnalysisDto ToSummaryDto(Analysis a) => Build(a, ParseSwingSummary(a.SwingJson));

    private static AnalysisDto Build(Analysis a, JsonElement? swing)
    {
        var v = a.Video;
        return new AnalysisDto(
            a.Id,
            a.Status,
            a.Progress,
            a.Stage,
            a.Error,
            a.CreatedAt,
            a.CompletedAt,
            a.PipelineVersion,
            a.PoseModel,
            new VideoDto(v.Id, v.OriginalFileName, v.CameraAngle, v.Handedness, v.Club,
                v.Width, v.Height, v.Fps, v.DurationSeconds, v.Orientation, v.UploadedAt),
            ParseJson(a.QualityJson),
            a.KeypointSet is null ? null : new KeypointsDto(a.KeypointSet.FrameCount, a.KeypointSet.DataFormat),
            swing);
    }

    private static JsonElement? ParseJson(string? json)
    {
        if (string.IsNullOrEmpty(json)) return null;
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }

    private static JsonElement? ParseSwingSummary(string? json)
    {
        if (string.IsNullOrEmpty(json)) return null;
        if (JsonNode.Parse(json) is not JsonObject swing) return ParseJson(json);
        swing.Remove("rejected_landmarks");
        (swing["club"] as JsonObject)?.Remove("track");
        return JsonSerializer.SerializeToElement(swing);
    }
}
