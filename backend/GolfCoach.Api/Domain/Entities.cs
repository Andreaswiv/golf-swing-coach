namespace GolfCoach.Api.Domain;

public enum CameraAngle { FaceOn, DownTheLine }

public enum Handedness { Right, Left }

public enum AnalysisStatus { Queued, Processing, Completed, Failed }

/// <summary>Measured = a 2D value taken directly from keypoints. Estimated = a derived indicator.</summary>
public enum MeasurementType { Measured, Estimated }

public class Video
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public string OriginalFileName { get; set; } = "";

    /// <summary>Path relative to the shared data directory, e.g. videos/{id}.mp4.</summary>
    public string StoredPath { get; set; } = "";

    public long FileSizeBytes { get; set; }
    public CameraAngle CameraAngle { get; set; }
    public Handedness Handedness { get; set; }
    public string? Club { get; set; }

    // Filled in from the computer-vision service once it has probed the file.
    public int? Width { get; set; }
    public int? Height { get; set; }
    public double? Fps { get; set; }
    public double? DurationSeconds { get; set; }
    public int? FrameCount { get; set; }
    public string? Orientation { get; set; }

    public DateTime UploadedAt { get; set; } = DateTime.UtcNow;

    public List<Analysis> Analyses { get; set; } = [];
}

public class Analysis
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid VideoId { get; set; }
    public Video Video { get; set; } = null!;

    public AnalysisStatus Status { get; set; } = AnalysisStatus.Queued;
    public int Progress { get; set; }
    public string Stage { get; set; } = "Queued";
    public string? Error { get; set; }

    public string? PipelineVersion { get; set; }
    public string? PoseModel { get; set; }

    /// <summary>Quality report from the CV service, stored as jsonb.</summary>
    public string? QualityJson { get; set; }

    /// <summary>
    /// Full swing analysis result from the CV service (status, notes, phases, measurements), stored as jsonb.
    /// Phases and Measurements below hold the same numbers as rows, for querying across swings.
    /// </summary>
    public string? SwingJson { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }

    public KeypointSet? KeypointSet { get; set; }
    public List<Phase> Phases { get; set; } = [];
    public List<Measurement> Measurements { get; set; } = [];
}

/// <summary>Points at the per-frame keypoint JSON file. The keypoints themselves never live in the database.</summary>
public class KeypointSet
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AnalysisId { get; set; }
    public Analysis Analysis { get; set; } = null!;

    public string FilePath { get; set; } = "";
    public int FrameCount { get; set; }
    public string DataFormat { get; set; } = "";
}

/// <summary>A detected swing event (address, takeaway, top, impact, finish). Written by the swing analysis.</summary>
public class Phase
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AnalysisId { get; set; }
    public Analysis Analysis { get; set; } = null!;

    public string Name { get; set; } = "";
    public int FrameIndex { get; set; }
    public double TimestampSeconds { get; set; }
    public string DetectionMethod { get; set; } = "";
    public double Confidence { get; set; }
}

public class Measurement
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid AnalysisId { get; set; }
    public Analysis Analysis { get; set; } = null!;

    public string Name { get; set; } = "";
    public string? Phase { get; set; }
    public int FrameIndex { get; set; }
    public double Value { get; set; }
    public string Unit { get; set; } = "";
    public CameraAngle CameraAngle { get; set; }
    public MeasurementType Type { get; set; }
    public double Confidence { get; set; }
}
