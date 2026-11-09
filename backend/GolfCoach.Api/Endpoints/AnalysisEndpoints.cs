using System.Text.Json;
using GolfCoach.Api.Contracts;
using GolfCoach.Api.Data;
using GolfCoach.Api.Domain;
using GolfCoach.Api.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace GolfCoach.Api.Endpoints;

public static class AnalysisEndpoints
{
    public static IEndpointRouteBuilder MapAnalysisEndpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/analyses");

        // Antiforgery is disabled because this is a local, single-user app without cookies or login.
        // Revisit when authentication is added.
        group.MapPost("/", Create).DisableAntiforgery();
        group.MapGet("/", List);
        group.MapGet("/{id:guid}", Get);
        group.MapGet("/{id:guid}/video", GetVideo);
        group.MapGet("/{id:guid}/keypoints", GetKeypoints);
        group.MapPost("/reanalyze", ReanalyzeAll);
        group.MapPost("/{id:guid}/reanalyze", Reanalyze);
        group.MapDelete("/{id:guid}", Delete);
        return app;
    }

    private static IQueryable<Analysis> WithDetails(AppDbContext db) =>
        db.Analyses.Include(a => a.Video).Include(a => a.KeypointSet);

    private static async Task<IResult> Create(
        [FromForm] IFormFile? video,
        [FromForm] string? cameraAngle,
        [FromForm] string? handedness,
        [FromForm] string? club,
        AppDbContext db,
        StoragePaths storage,
        IAnalysisQueue queue,
        IOptions<UploadOptions> uploadOptions,
        CancellationToken ct)
    {
        var maxBytes = uploadOptions.Value.MaxBytes;

        var fileProblem = UploadValidator.ValidateFile(video?.FileName, video?.Length ?? 0, maxBytes);
        if (fileProblem is not null) return Results.Problem(detail: fileProblem, statusCode: 400, title: "Invalid video");
        if (!WireFormat.TryParseCameraAngle(cameraAngle, out var angle))
            return Results.Problem(detail: "cameraAngle must be \"face_on\" or \"down_the_line\".", statusCode: 400, title: "Invalid camera angle");
        if (!WireFormat.TryParseHandedness(handedness, out var hand))
            return Results.Problem(detail: "handedness must be \"right\" or \"left\".", statusCode: 400, title: "Invalid handedness");

        // video is non-null here (ValidateFile rejected a missing file).
        var file = video!;

        var header = new byte[12];
        await using (var probe = file.OpenReadStream())
        {
            var read = await probe.ReadAtLeastAsync(header, header.Length, throwOnEndOfStream: false, ct);
            if (!UploadValidator.LooksLikeMp4OrMov(header.AsSpan(0, read)))
                return Results.Problem(detail: "This does not look like an MP4 or MOV video file.", statusCode: 400, title: "Invalid video");
        }

        var entity = new Video
        {
            OriginalFileName = TrimTo(Path.GetFileName(file.FileName), 255),
            CameraAngle = angle,
            Handedness = hand,
            Club = string.IsNullOrWhiteSpace(club) ? null : TrimTo(club.Trim(), 60),
            FileSizeBytes = file.Length,
        };
        entity.StoredPath = storage.VideoRelativePath(entity.Id, Path.GetExtension(file.FileName));
        var absolute = storage.Resolve(entity.StoredPath);
        Directory.CreateDirectory(Path.GetDirectoryName(absolute)!);

        try
        {
            await using (var target = new FileStream(absolute, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, useAsync: true))
            {
                await file.CopyToAsync(target, ct);
            }

            var analysis = new Analysis { Video = entity, VideoId = entity.Id };
            db.Videos.Add(entity);
            db.Analyses.Add(analysis);
            await db.SaveChangesAsync(ct);

            queue.Enqueue(analysis.Id);
            return Results.Created($"/api/analyses/{analysis.Id}", DtoMapper.ToDto(analysis));
        }
        catch
        {
            storage.TryDelete(entity.StoredPath); // do not leave half-saved uploads behind
            throw;
        }
    }

    private static async Task<IResult> List(AppDbContext db, CancellationToken ct)
    {
        var items = await WithDetails(db).AsNoTracking().OrderByDescending(a => a.CreatedAt).ToListAsync(ct);
        return Results.Ok(items.Select(DtoMapper.ToSummaryDto));
    }

    private static async Task<IResult> Get(Guid id, AppDbContext db, CancellationToken ct)
    {
        var analysis = await WithDetails(db).AsNoTracking().FirstOrDefaultAsync(a => a.Id == id, ct);
        return analysis is null ? NotFound(id) : Results.Ok(DtoMapper.ToDto(analysis));
    }

    private static async Task<IResult> GetVideo(Guid id, AppDbContext db, StoragePaths storage, CancellationToken ct)
    {
        var video = await db.Analyses.AsNoTracking().Where(a => a.Id == id).Select(a => a.Video).FirstOrDefaultAsync(ct);
        if (video is null) return NotFound(id);

        var path = storage.Resolve(video.StoredPath);
        if (!File.Exists(path)) return Results.Problem(detail: "The video file is missing from disk.", statusCode: 404);

        var contentType = Path.GetExtension(path).ToLowerInvariant() == ".mov" ? "video/quicktime" : "video/mp4";
        // Range processing lets the browser seek and scrub without downloading the whole file.
        return Results.File(path, contentType, enableRangeProcessing: true);
    }

    private static async Task<IResult> GetKeypoints(Guid id, AppDbContext db, StoragePaths storage, CancellationToken ct)
    {
        var set = await db.KeypointSets.AsNoTracking().FirstOrDefaultAsync(k => k.AnalysisId == id, ct);
        if (set is null) return Results.Problem(detail: "No keypoints exist for this analysis (yet).", statusCode: 404);

        var path = storage.Resolve(set.FilePath);
        if (!File.Exists(path)) return Results.Problem(detail: "The keypoints file is missing from disk.", statusCode: 404);
        return Results.File(path, "application/json");
    }

    /// <summary>Re-runs the swing analysis on every finished swing, for after a change to the analysis code or limits.</summary>
    private static async Task<IResult> ReanalyzeAll(AppDbContext db, ICvServiceClient cv, ILoggerFactory loggers, CancellationToken ct)
    {
        var analyses = await db.Analyses.Include(a => a.KeypointSet)
            .Where(a => a.Status == AnalysisStatus.Completed && a.KeypointSet != null)
            .ToListAsync(ct);

        var log = loggers.CreateLogger("ReanalyzeAll");
        var failed = 0;
        foreach (var analysis in analyses)
        {
            try
            {
                var swing = await cv.AnalyzeAsync(analysis.KeypointSet!.FilePath, ct);
                analysis.SwingJson = swing.GetRawText();
                await db.SaveChangesAsync(ct);
            }
            catch (Exception ex) when (ex is CvServiceException or HttpRequestException)
            {
                failed++; // one bad file must not stop the rest
                log.LogWarning(ex, "Could not re-analyse {Id}.", analysis.Id);
            }
        }
        return Results.Ok(new ReanalyzeAllDto(analyses.Count - failed, failed));
    }

    /// <summary>Re-runs the swing analysis from the saved keypoints, replacing the stored result.</summary>
    private static async Task<IResult> Reanalyze(Guid id, AppDbContext db, ICvServiceClient cv, CancellationToken ct)
    {
        var analysis = await WithDetails(db).FirstOrDefaultAsync(a => a.Id == id, ct);
        if (analysis is null) return NotFound(id);
        if (analysis.Status != AnalysisStatus.Completed || analysis.KeypointSet is null)
            return Results.Problem(detail: "Only finished analyses with keypoints can be re-analysed.", statusCode: 409,
                title: "Analysis not finished");

        JsonElement swing;
        try
        {
            swing = await cv.AnalyzeAsync(analysis.KeypointSet.FilePath, ct);
        }
        catch (CvServiceException ex)
        {
            return Results.Problem(detail: ex.Message, statusCode: 502, title: "Swing analysis failed");
        }
        catch (HttpRequestException)
        {
            return Results.Problem(detail: "The computer-vision service could not be reached.", statusCode: 503,
                title: "CV service unavailable");
        }

        analysis.SwingJson = swing.GetRawText();
        await db.SaveChangesAsync(ct);
        return Results.Ok(DtoMapper.ToDto(analysis));
    }

    private static async Task<IResult> Delete(
        Guid id, AppDbContext db, StoragePaths storage, ILoggerFactory loggers, CancellationToken ct)
    {
        var analysis = await WithDetails(db).FirstOrDefaultAsync(a => a.Id == id, ct);
        if (analysis is null) return NotFound(id);

        if (analysis.Status is AnalysisStatus.Queued or AnalysisStatus.Processing)
            return Results.Problem(
                detail: "This analysis is still processing. Wait for it to finish, then delete it.",
                statusCode: 409, title: "Analysis in progress");

        var video = analysis.Video;
        var keypointsPath = analysis.KeypointSet?.FilePath ?? storage.KeypointsRelativePath(analysis.Id);
        var videoShared = await db.Analyses.AnyAsync(a => a.VideoId == video.Id && a.Id != analysis.Id, ct);

        db.Analyses.Remove(analysis); // cascades to the keypoint set
        if (!videoShared) db.Videos.Remove(video);
        await db.SaveChangesAsync(ct);

        var log = loggers.CreateLogger("Delete");
        var ok = storage.TryDelete(keypointsPath);
        if (!videoShared) ok &= storage.TryDelete(video.StoredPath);
        if (!ok) log.LogWarning("Analysis {Id} was deleted from the database but some files could not be removed.", id);

        return Results.NoContent();
    }

    private static IResult NotFound(Guid id) =>
        Results.Problem(detail: $"No analysis with id {id}.", statusCode: 404, title: "Not found");

    private static string TrimTo(string value, int max) => value.Length <= max ? value : value[..max];
}
