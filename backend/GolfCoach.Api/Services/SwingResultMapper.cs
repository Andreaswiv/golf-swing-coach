using System.Text.Json;
using GolfCoach.Api.Data;
using GolfCoach.Api.Domain;

namespace GolfCoach.Api.Services;

/// <summary>Stores a swing analysis result from the CV service: the whole JSON plus phase and measurement rows.</summary>
public static class SwingResultMapper
{
    /// <summary>
    /// Replaces any previous swing result of <paramref name="analysis"/>. Phases and Measurements must be loaded
    /// (or known to be empty) so the old rows are removed.
    /// </summary>
    public static void Apply(AppDbContext db, Analysis analysis, JsonElement swing)
    {
        var parsed = swing.Deserialize<CvSwing>(CvServiceClient.Json)
                     ?? throw new InvalidOperationException("The swing analysis result was empty.");

        db.Phases.RemoveRange(analysis.Phases);
        db.Measurements.RemoveRange(analysis.Measurements);
        analysis.SwingJson = swing.GetRawText();

        db.Phases.AddRange(parsed.Phases.Select(p => new Phase
        {
            AnalysisId = analysis.Id,
            Name = Trim(p.Name, 40),
            FrameIndex = p.FrameIndex,
            TimestampSeconds = p.TimestampS,
            DetectionMethod = Trim(p.Method, 60),
            Confidence = p.Confidence,
        }));
        db.Measurements.AddRange(parsed.Measurements.Select(m => new Measurement
        {
            AnalysisId = analysis.Id,
            Name = Trim(m.Name, 80),
            Phase = m.Phase is null ? null : Trim(m.Phase, 40),
            FrameIndex = m.FrameIndex,
            Value = m.Value,
            Unit = Trim(m.Unit, 20),
            CameraAngle = analysis.Video.CameraAngle,
            Type = m.Type == "measured" ? MeasurementType.Measured : MeasurementType.Estimated,
            Confidence = m.Confidence,
        }));
    }

    private static string Trim(string value, int max) => value.Length <= max ? value : value[..max];
}
