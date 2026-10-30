using GolfCoach.Api.Services;
using Xunit;

namespace GolfCoach.Api.Tests;

public class UploadValidatorTests
{
    private const long Max = 500L * 1024 * 1024;

    [Theory]
    [InlineData("swing.mp4")]
    [InlineData("SWING.MOV")]
    [InlineData("clip.m4v")]
    public void Accepts_supported_extensions(string name) =>
        Assert.Null(UploadValidator.ValidateFile(name, 1024, Max));

    [Theory]
    [InlineData("swing.avi")]
    [InlineData("swing.exe")]
    [InlineData("swing")]
    public void Rejects_unsupported_extensions(string name) =>
        Assert.NotNull(UploadValidator.ValidateFile(name, 1024, Max));

    [Fact]
    public void Rejects_missing_empty_and_oversized_files()
    {
        Assert.NotNull(UploadValidator.ValidateFile(null, 1024, Max));
        Assert.NotNull(UploadValidator.ValidateFile("a.mp4", 0, Max));
        Assert.NotNull(UploadValidator.ValidateFile("a.mp4", Max + 1, Max));
    }

    [Fact]
    public void Recognises_mp4_and_mov_headers()
    {
        byte[] Header(string atom) => [0, 0, 0, 0x20, .. System.Text.Encoding.ASCII.GetBytes(atom), 0, 0, 0, 0];

        Assert.True(UploadValidator.LooksLikeMp4OrMov(Header("ftyp")));
        Assert.True(UploadValidator.LooksLikeMp4OrMov(Header("moov")));
        Assert.False(UploadValidator.LooksLikeMp4OrMov(Header("RIFF")));
        Assert.False(UploadValidator.LooksLikeMp4OrMov(new byte[4]));
    }
}
