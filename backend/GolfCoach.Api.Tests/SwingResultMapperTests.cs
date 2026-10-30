using System.Text.Json;
using GolfCoach.Api.Contracts;
using GolfCoach.Api.Data;
using GolfCoach.Api.Domain;
using GolfCoach.Api.Services;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace GolfCoach.Api.Tests;

/// <summary>Swing results from the CV service become JSON plus Phase and Measurement rows.</summary>
public class SwingResultMapperTests
{
    // Shape copied from cv-service/app/swing/__init__.py (analyse_swing).
    private const string SwingJson = """
    {
      "version": "swing-0.1", "status": "ok", "camera_angle": "down_the_line", "mirrored_for_left_handed": false,
      "smoothing": {"method": "savitzky_golay", "window_frames": 5, "polyorder": 2},
      "phases": [
        {"name": "address", "frame_index": 34, "timestamp_s": 1.1333, "method": "middle_of_last_rest_at_held_hand_position", "confidence": 1.0},
        {"name": "impact", "frame_index": 229, "timestamp_s": 7.6333, "method": "lowest_hands_after_fastest_downswing", "confidence": 0.48}
      ],
      "measurements": [
        {"name": "spine_angle_address", "phase": "address", "frame_index": 34, "value": 40.1, "unit": "deg", "type": "measured", "confidence": 1.0},
        {"name": "tempo_ratio", "phase": "top", "frame_index": 175, "value": 3.1, "unit": "ratio", "type": "estimated", "confidence": 0.5}
      ],
      "notes": [{"code": "slow_motion_suspected", "message": "..."}]
    }
    """;

    // Model building and change tracking work without a database connection.
    private static AppDbContext OfflineDb() =>
        new(new DbContextOptionsBuilder<AppDbContext>().UseNpgsql("Host=unused").Options);

    private static Analysis NewAnalysis()
    {
        var video = new Video { CameraAngle = CameraAngle.DownTheLine };
        return new Analysis { Video = video, VideoId = video.Id };
    }

    [Fact]
    public void Stores_json_and_rows()
    {
        using var db = OfflineDb();
        var analysis = NewAnalysis();
        using var doc = JsonDocument.Parse(SwingJson);

        SwingResultMapper.Apply(db, analysis, doc.RootElement);

        Assert.Contains("slow_motion_suspected", analysis.SwingJson);
        var phases = db.ChangeTracker.Entries<Phase>().Select(e => e.Entity).ToList();
        Assert.Equal(["address", "impact"], phases.Select(p => p.Name));
        Assert.Equal(7.6333, phases[1].TimestampSeconds);
        Assert.Equal("lowest_hands_after_fastest_downswing", phases[1].DetectionMethod);
        Assert.All(phases, p => Assert.Equal(analysis.Id, p.AnalysisId));

        var measurements = db.ChangeTracker.Entries<Measurement>().Select(e => e.Entity).ToList();
        var spine = measurements.Single(m => m.Name == "spine_angle_address");
        Assert.Equal(MeasurementType.Measured, spine.Type);
        Assert.Equal(CameraAngle.DownTheLine, spine.CameraAngle);
        Assert.Equal(40.1, spine.Value);
        Assert.Equal(MeasurementType.Estimated, measurements.Single(m => m.Name == "tempo_ratio").Type);
    }

    [Fact]
    public void Re_applying_replaces_previous_rows()
    {
        using var db = OfflineDb();
        var analysis = NewAnalysis();
        var old = new Phase { AnalysisId = analysis.Id, Name = "top" };
        analysis.Phases.Add(old);
        db.Attach(old);
        using var doc = JsonDocument.Parse(SwingJson);

        SwingResultMapper.Apply(db, analysis, doc.RootElement);

        Assert.Equal(EntityState.Deleted, db.Entry(old).State);
        Assert.Equal(2, db.ChangeTracker.Entries<Phase>().Count(e => e.State == EntityState.Added));
    }

    [Fact]
    public void Analysis_dto_passes_swing_json_through()
    {
        var analysis = NewAnalysis();
        analysis.SwingJson = SwingJson;

        var dto = DtoMapper.ToDto(analysis);

        Assert.Equal("ok", dto.Swing!.Value.GetProperty("status").GetString());
        Assert.Equal(2, dto.Swing.Value.GetProperty("phases").GetArrayLength());
    }

    [Fact]
    public void Cv_result_without_swing_still_parses()
    {
        const string json = """{"pipeline_version":"0.2.0","pose_model":"m","video":{"width":1,"height":1,"fps":30,"declared_frame_count":1,"duration_seconds":1,"orientation":"portrait","rotation_degrees":0,"codec":"avc1"},"keypoints":{"path":"k","frame_count":1,"data_format":"f"},"quality":{}}""";
        var result = JsonSerializer.Deserialize<CvResult>(json, CvServiceClient.Json)!;
        Assert.Null(result.Swing);
    }
}
