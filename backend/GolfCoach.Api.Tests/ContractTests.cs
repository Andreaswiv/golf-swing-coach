using System.Text.Json;
using GolfCoach.Api.Contracts;
using GolfCoach.Api.Domain;
using GolfCoach.Api.Services;
using Xunit;

namespace GolfCoach.Api.Tests;

/// <summary>Guards the JSON contracts with the Python service and the React frontend.</summary>
public class ContractTests
{
    [Fact]
    public void Wire_format_round_trips()
    {
        Assert.Equal("face_on", CameraAngle.FaceOn.ToWire());
        Assert.Equal("down_the_line", CameraAngle.DownTheLine.ToWire());
        Assert.Equal("left", Handedness.Left.ToWire());

        Assert.True(WireFormat.TryParseCameraAngle("down_the_line", out var a) && a == CameraAngle.DownTheLine);
        Assert.True(WireFormat.TryParseHandedness(" Right ", out var h) && h == Handedness.Right);
        Assert.False(WireFormat.TryParseCameraAngle("overhead", out _));
        Assert.False(WireFormat.TryParseHandedness(null, out _));
    }

    [Fact]
    public void Cv_job_request_serialises_as_snake_case()
    {
        var json = JsonSerializer.Serialize(
            new CvJobRequest("abc", "videos/a.mp4", "keypoints/a.json", "face_on", "right"), CvServiceClient.Json);

        Assert.Contains("\"analysis_id\":\"abc\"", json);
        Assert.Contains("\"video_path\":\"videos/a.mp4\"", json);
        Assert.Contains("\"keypoints_path\":\"keypoints/a.json\"", json);
        Assert.Contains("\"camera_angle\":\"face_on\"", json);
    }

    [Fact]
    public void Cv_job_state_parses_what_the_python_service_returns()
    {
        // Shape copied from cv-service/app/jobs.py (JobState + result).
        const string json = """
        {
          "job_id": "j1", "analysis_id": "a1", "status": "completed", "progress": 100, "stage": "Completed", "error": null,
          "result": {
            "pipeline_version": "0.2.0",
            "pose_model": "mediapipe-pose-landmarker:pose_landmarker_full",
            "video": {"width":1920,"height":1080,"fps":60.0,"declared_frame_count":180,"duration_seconds":3.0,
                      "orientation":"landscape","rotation_degrees":0,"codec":"avc1"},
            "keypoints": {"path":"keypoints/a1.json","frame_count":180,"data_format":"golfcoach.keypoints.v1"},
            "quality": {"overall":"good","warnings":[],"stats":{},"checks_not_run":["camera_motion"]}
          }
        }
        """;

        var state = JsonSerializer.Deserialize<CvJobState>(json, CvServiceClient.Json)!;

        Assert.Equal("completed", state.Status);
        Assert.Equal(1920, state.Result!.Video.Width);
        Assert.Equal(180, state.Result.Keypoints.FrameCount);
        Assert.Equal("good", state.Result.Quality.GetProperty("overall").GetString());
    }

    [Fact]
    public void Analysis_dto_uses_camel_case_properties_and_snake_case_enums()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower));

        var video = new Video { OriginalFileName = "swing.mp4", CameraAngle = CameraAngle.DownTheLine, Handedness = Handedness.Left };
        var analysis = new Analysis
        {
            Video = video, VideoId = video.Id, Status = AnalysisStatus.Processing,
            QualityJson = """{"overall":"warning","warnings":[],"stats":{},"checks_not_run":[]}""",
        };

        var json = JsonSerializer.Serialize(DtoMapper.ToDto(analysis), options);

        Assert.Contains("\"status\":\"processing\"", json);
        Assert.Contains("\"cameraAngle\":\"down_the_line\"", json);
        Assert.Contains("\"originalFileName\":\"swing.mp4\"", json);
        Assert.Contains("\"checks_not_run\":[]", json); // quality passes through untouched
    }
}
