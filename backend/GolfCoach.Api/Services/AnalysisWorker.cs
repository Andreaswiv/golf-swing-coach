using System.Text.Json;
using GolfCoach.Api.Data;
using GolfCoach.Api.Domain;
using Microsoft.EntityFrameworkCore;

namespace GolfCoach.Api.Services;

/// <summary>
/// Background worker: takes queued analyses, submits them to the CV service, polls its job status
/// (copying progress into the database so the frontend can poll the API), and stores the result.
/// </summary>
public sealed class AnalysisWorker(
    IServiceScopeFactory scopes,
    IAnalysisQueue queue,
    ILogger<AnalysisWorker> log) : BackgroundService
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan JobTimeout = TimeSpan.FromMinutes(30);
    private const int MaxSubmitAttempts = 12;      // CV service may still be starting
    private const int MaxConsecutivePollErrors = 60;
    private const int MaxResubmits = 3;            // CV service restarts that we will recover from

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        await Task.Yield(); // let host startup finish first
        await RequeueUnfinishedAsync(ct);

        try
        {
            await foreach (var id in queue.Reader.ReadAllAsync(ct))
            {
                try
                {
                    await ProcessAsync(id, ct);
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested)
                {
                    break; // shutting down; the analysis stays Processing and is re-queued on next start
                }
                catch (CvServiceException ex)
                {
                    log.LogError(ex, "CV service refused analysis {Id}.", id);
                    await MarkFailedAsync(id, ex.Message, CancellationToken.None);
                }
                catch (Exception ex)
                {
                    log.LogError(ex, "Analysis {Id} failed unexpectedly.", id);
                    await MarkFailedAsync(id, $"Unexpected error: {ex.Message}", CancellationToken.None);
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            // normal shutdown
        }
    }

    private async Task RequeueUnfinishedAsync(CancellationToken ct)
    {
        try
        {
            using var scope = scopes.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var ids = await db.Analyses
                .Where(a => a.Status == AnalysisStatus.Queued || a.Status == AnalysisStatus.Processing)
                .OrderBy(a => a.CreatedAt)
                .Select(a => a.Id)
                .ToListAsync(ct);
            foreach (var id in ids) queue.Enqueue(id);
            if (ids.Count > 0) log.LogInformation("Re-queued {Count} unfinished analyses.", ids.Count);
        }
        catch (Exception ex) when (!ct.IsCancellationRequested)
        {
            log.LogError(ex, "Could not re-queue unfinished analyses.");
        }
    }

    private async Task ProcessAsync(Guid id, CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var cv = scope.ServiceProvider.GetRequiredService<ICvServiceClient>();
        var storage = scope.ServiceProvider.GetRequiredService<StoragePaths>();

        var analysis = await db.Analyses.Include(a => a.Video).FirstOrDefaultAsync(a => a.Id == id, ct);
        if (analysis is null || analysis.Status is AnalysisStatus.Completed or AnalysisStatus.Failed)
            return; // deleted or already finished

        analysis.Status = AnalysisStatus.Processing;
        analysis.StartedAt ??= DateTime.UtcNow;
        analysis.Progress = Math.Max(analysis.Progress, 1);
        analysis.Stage = "Starting";
        await db.SaveChangesAsync(ct);

        var request = new CvJobRequest(
            analysis.Id.ToString("N"),
            analysis.Video.StoredPath,
            storage.KeypointsRelativePath(analysis.Id),
            analysis.Video.CameraAngle.ToWire(),
            analysis.Video.Handedness.ToWire());

        var job = await SubmitWithRetryAsync(cv, request, ct);
        if (job is null)
        {
            await FailAsync(db, analysis, "The computer-vision service could not be reached. Check that it is running and try again.", ct);
            return;
        }

        var deadline = DateTime.UtcNow + JobTimeout;
        var resubmits = 0;
        var pollErrors = 0;

        while (true)
        {
            if (DateTime.UtcNow > deadline)
            {
                await FailAsync(db, analysis, "Processing took longer than 30 minutes and was stopped.", ct);
                return;
            }

            await Task.Delay(PollInterval, ct);

            CvJobState? state;
            try
            {
                state = await cv.GetJobAsync(job.JobId, ct);
                pollErrors = 0;
            }
            catch (Exception ex) when (IsTransient(ex, ct))
            {
                if (++pollErrors >= MaxConsecutivePollErrors)
                {
                    await FailAsync(db, analysis, "Lost contact with the computer-vision service.", ct);
                    return;
                }
                continue;
            }

            if (state is null)
            {
                // CV service restarted and forgot the job: submit again.
                if (++resubmits > MaxResubmits)
                {
                    await FailAsync(db, analysis, "The computer-vision service kept restarting during processing.", ct);
                    return;
                }
                log.LogWarning("CV service lost job {Job}; resubmitting analysis {Id}.", job.JobId, id);
                job = await SubmitWithRetryAsync(cv, request, ct);
                if (job is null)
                {
                    await FailAsync(db, analysis, "The computer-vision service could not be reached.", ct);
                    return;
                }
                continue;
            }

            switch (state.Status)
            {
                case "completed":
                    await CompleteAsync(db, analysis, state, ct);
                    return;
                case "failed":
                    await FailAsync(db, analysis, state.Error ?? "The video could not be processed.", ct);
                    return;
                default:
                    if (state.Progress != analysis.Progress || state.Stage != analysis.Stage)
                    {
                        analysis.Progress = Math.Clamp(state.Progress, 0, 99);
                        analysis.Stage = state.Stage;
                        await db.SaveChangesAsync(ct);
                    }
                    break;
            }
        }
    }

    private static bool IsTransient(Exception ex, CancellationToken ct) =>
        !ct.IsCancellationRequested && (ex is HttpRequestException || ex is TaskCanceledException);

    private async Task<CvJobState?> SubmitWithRetryAsync(ICvServiceClient cv, CvJobRequest request, CancellationToken ct)
    {
        for (var attempt = 1; attempt <= MaxSubmitAttempts; attempt++)
        {
            try
            {
                return await cv.SubmitJobAsync(request, ct);
            }
            catch (CvServiceException)
            {
                throw; // the service understood and refused: retrying will not help
            }
            catch (Exception ex) when (IsTransient(ex, ct))
            {
                log.LogWarning("CV service not reachable (attempt {Attempt}/{Max}): {Message}", attempt, MaxSubmitAttempts, ex.Message);
                await Task.Delay(TimeSpan.FromSeconds(5), ct);
            }
        }
        return null;
    }

    private static async Task CompleteAsync(AppDbContext db, Analysis analysis, CvJobState state, CancellationToken ct)
    {
        var result = state.Result ?? throw new InvalidOperationException("CV service reported completion without a result.");

        var video = analysis.Video;
        video.Width = result.Video.Width;
        video.Height = result.Video.Height;
        video.Fps = result.Video.Fps;
        video.DurationSeconds = result.Video.DurationSeconds;
        video.FrameCount = result.Keypoints.FrameCount;
        video.Orientation = result.Video.Orientation;

        analysis.PipelineVersion = result.PipelineVersion;
        analysis.PoseModel = result.PoseModel;
        analysis.QualityJson = result.Quality.GetRawText();
        analysis.KeypointSet = new KeypointSet
        {
            AnalysisId = analysis.Id,
            FilePath = result.Keypoints.Path,
            FrameCount = result.Keypoints.FrameCount,
            DataFormat = result.Keypoints.DataFormat,
        };
        if (result.Swing is { ValueKind: JsonValueKind.Object } swing)
            SwingResultMapper.Apply(db, analysis, swing);
        analysis.Status = AnalysisStatus.Completed;
        analysis.Progress = 100;
        analysis.Stage = "Completed";
        analysis.Error = null;
        analysis.CompletedAt = DateTime.UtcNow;
        await db.SaveChangesAsync(ct);
    }

    private static async Task FailAsync(AppDbContext db, Analysis analysis, string message, CancellationToken ct)
    {
        analysis.Status = AnalysisStatus.Failed;
        analysis.Stage = "Failed";
        analysis.Error = message.Length > 1900 ? message[..1900] : message;
        analysis.CompletedAt = DateTime.UtcNow;
        await db.SaveChangesAsync(ct);
    }

    private async Task MarkFailedAsync(Guid id, string message, CancellationToken ct)
    {
        try
        {
            using var scope = scopes.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
            var analysis = await db.Analyses.FirstOrDefaultAsync(a => a.Id == id, ct);
            if (analysis is not null && analysis.Status is not AnalysisStatus.Completed)
                await FailAsync(db, analysis, message, ct);
        }
        catch (Exception ex)
        {
            log.LogError(ex, "Could not record failure for analysis {Id}.", id);
        }
    }
}
