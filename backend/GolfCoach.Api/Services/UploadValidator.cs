using System.Text;

namespace GolfCoach.Api.Services;

/// <summary>
/// Cheap checks done before a file is accepted. Whether the video can really be decoded is decided
/// by the CV service (OpenCV), which reports a readable error if it cannot.
/// </summary>
public static class UploadValidator
{
    public static readonly string[] AllowedExtensions = [".mp4", ".mov", ".m4v"];

    public static string? ValidateFile(string? fileName, long length, long maxBytes)
    {
        if (string.IsNullOrWhiteSpace(fileName))
            return "No video file was provided.";

        var ext = Path.GetExtension(fileName).ToLowerInvariant();
        if (!AllowedExtensions.Contains(ext))
            return $"Unsupported file type \"{ext}\". Upload an MP4 or MOV file.";

        if (length <= 0)
            return "The uploaded file is empty.";

        if (length > maxBytes)
            return $"The file is {length / 1024 / 1024} MB; the limit is {maxBytes / 1024 / 1024} MB. Trim the clip to the swing.";

        return null;
    }

    /// <summary>
    /// MP4 and MOV are ISO base media / QuickTime files: an atom size (4 bytes) followed by an atom type.
    /// This catches renamed non-video files without trying to be a full parser.
    /// </summary>
    public static bool LooksLikeMp4OrMov(ReadOnlySpan<byte> header)
    {
        if (header.Length < 12) return false;
        var atom = Encoding.ASCII.GetString(header.Slice(4, 4));
        return atom is "ftyp" or "moov" or "mdat" or "wide" or "free" or "skip";
    }
}
