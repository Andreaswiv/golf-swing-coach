using System.Text.Json;
using GolfCoach.Api.Contracts;
using GolfCoach.Api.Domain;
using GolfCoach.Api.Services;
using Xunit;

namespace GolfCoach.Api.Tests;

/// <summary>Swing results from the CV service are stored as JSON and passed through to the frontend.</summary>
public class DtoMapperTests
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

    private static Analysis NewAnalysis()
    {
        var video = new Video { CameraAngle = CameraAngle.DownTheLine };
        return new Analysis { Video = video, VideoId = video.Id };
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
    public void Summary_dto_leaves_out_per_frame_data_only()
    {
        var analysis = NewAnalysis();
        analysis.SwingJson = """
        {"status": "ok", "phases": [], "rejected_landmarks": {"left_wrist": [3]},
         "club": {"tracked": true, "track": [[0.1, 0.2, 0.3, 0.4, 1]], "plane": null}}
        """;

        var swing = DtoMapper.ToSummaryDto(analysis).Swing!.Value;

        Assert.Equal("ok", swing.GetProperty("status").GetString());
        Assert.False(swing.TryGetProperty("rejected_landmarks", out _));
        var club = swing.GetProperty("club");
        Assert.True(club.GetProperty("tracked").GetBoolean());
        Assert.False(club.TryGetProperty("track", out _));
    }

    [Fact]
    public void Cv_result_without_swing_still_parses()
    {
        const string json = """{"pipeline_version":"0.2.0","pose_model":"m","video":{"width":1,"height":1,"fps":30,"declared_frame_count":1,"duration_seconds":1,"orientation":"portrait","rotation_degrees":0,"codec":"avc1"},"keypoints":{"path":"k","frame_count":1,"data_format":"f"},"quality":{}}""";
        var result = JsonSerializer.Deserialize<CvResult>(json, CvServiceClient.Json)!;
        Assert.Null(result.Swing);
    }
}
