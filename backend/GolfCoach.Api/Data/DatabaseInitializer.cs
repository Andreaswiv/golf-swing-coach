using Microsoft.EntityFrameworkCore;

namespace GolfCoach.Api.Data;

/// <summary>
/// Brings the schema up to date on startup with EF Core migrations (Data/Migrations).
///
/// Databases created before migrations existed (by EnsureCreated, up to Milestone 2) already contain the
/// tables of the Initial migration but no migration history. Those are "baselined": the Initial migration is
/// recorded as applied without running it, and only the later migrations run. No data is touched.
/// </summary>
public static class DatabaseInitializer
{
    public static async Task InitialiseAsync(IServiceProvider services, ILogger logger, CancellationToken ct = default)
    {
        const int maxAttempts = 20;
        for (var attempt = 1; ; attempt++)
        {
            try
            {
                using var scope = services.CreateScope();
                var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
                await BaselineLegacyDatabaseAsync(db, logger, ct);
                await db.Database.MigrateAsync(ct);
                logger.LogInformation("Database ready.");
                return;
            }
            catch (Exception ex) when (attempt < maxAttempts && !ct.IsCancellationRequested)
            {
                // PostgreSQL may still be starting when the API container comes up.
                logger.LogWarning("Database not ready (attempt {Attempt}/{Max}): {Message}", attempt, maxAttempts, ex.Message);
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
            }
        }
    }

    private static async Task BaselineLegacyDatabaseAsync(AppDbContext db, ILogger logger, CancellationToken ct)
    {
        var historyExists = await ScalarAsync(db, """SELECT to_regclass('public."__EFMigrationsHistory"') IS NOT NULL AS "Value" """, ct);
        if (historyExists) return;

        var legacyTablesExist = await ScalarAsync(db, """SELECT to_regclass('public."Analyses"') IS NOT NULL AS "Value" """, ct);
        if (!legacyTablesExist) return; // empty database: MigrateAsync creates everything

        var initial = db.Database.GetMigrations().First();
        var productVersion = typeof(DbContext).Assembly.GetName().Version?.ToString(3) ?? "10.0.0";
        // One transaction: a half-done baseline (history table without the row) would make MigrateAsync
        // try to create tables that already exist.
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        await db.Database.ExecuteSqlRawAsync(
            """
            CREATE TABLE "__EFMigrationsHistory" (
                "MigrationId" character varying(150) NOT NULL PRIMARY KEY,
                "ProductVersion" character varying(32) NOT NULL);
            INSERT INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion") VALUES ({0}, {1});
            """,
            [initial, productVersion], ct);
        await tx.CommitAsync(ct);
        logger.LogInformation("Baselined a database created before migrations: marked {Migration} as applied.", initial);
    }

    private static async Task<bool> ScalarAsync(AppDbContext db, string sql, CancellationToken ct) =>
        await db.Database.SqlQueryRaw<bool>(sql).SingleAsync(ct);
}
