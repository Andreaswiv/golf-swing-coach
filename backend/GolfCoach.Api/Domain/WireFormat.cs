namespace GolfCoach.Api.Domain;

/// <summary>
/// Converts between the enums and the snake_case strings used on the wire
/// (frontend requests and the Python service).
/// </summary>
public static class WireFormat
{
    public static string ToWire(this CameraAngle a) => a switch
    {
        CameraAngle.FaceOn => "face_on",
        CameraAngle.DownTheLine => "down_the_line",
        _ => throw new ArgumentOutOfRangeException(nameof(a)),
    };

    public static string ToWire(this Handedness h) => h switch
    {
        Handedness.Right => "right",
        Handedness.Left => "left",
        _ => throw new ArgumentOutOfRangeException(nameof(h)),
    };

    public static bool TryParseCameraAngle(string? value, out CameraAngle angle)
    {
        switch (value?.Trim().ToLowerInvariant())
        {
            case "face_on": angle = CameraAngle.FaceOn; return true;
            case "down_the_line": angle = CameraAngle.DownTheLine; return true;
            default: angle = default; return false;
        }
    }

    public static bool TryParseHandedness(string? value, out Handedness hand)
    {
        switch (value?.Trim().ToLowerInvariant())
        {
            case "right": hand = Handedness.Right; return true;
            case "left": hand = Handedness.Left; return true;
            default: hand = default; return false;
        }
    }
}
