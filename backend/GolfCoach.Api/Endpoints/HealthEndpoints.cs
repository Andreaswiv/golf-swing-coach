using GolfCoach.Api.Contracts;
using GolfCoach.Api.Data;
using GolfCoach.Api.Services;

namespace GolfCoach.Api.Endpoints;

public static class HealthEndpoints
{
    public static IEndpointRouteBuilder MapHealthEndpoints(this IEndpointRouteBuilder app)
    {
        // Liveness: the API process is up. Used by scripts; does not touch dependencies.
        app.MapGet("/api/health/live", () => Results.Ok(new { status = "ok" }));

        // Readiness: reports each dependency separately, always with HTTP 200 so the UI can explain what is wrong.
        app.MapGet("/api/health", async (AppDbContext db, ICvServiceClient cv, CancellationToken ct) =>
        {
            var dbOk = false;
            try { dbOk = await db.Database.CanConnectAsync(ct); } catch { /* reported as false */ }

            var cvHealth = await cv.GetHealthAsync(ct);
            var ready = dbOk && cvHealth is { PoseModelPresent: true };
            return Results.Ok(new HealthDto(ready ? "ok" : "degraded", dbOk, cvHealth is not null, cvHealth?.PoseModelPresent));
        });
        return app;
    }
}
