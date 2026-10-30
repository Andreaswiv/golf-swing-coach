using System.Text.Json;
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
    public static AnalysisDto ToDto(Analysis a)
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
            ParseJson(a.SwingJson));
    }

    private static JsonElement? ParseJson(string? json)
    {
        if (string.IsNullOrEmpty(json)) return null;
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }
}
