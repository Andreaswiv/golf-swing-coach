using GolfCoach.Api.Domain;
using Microsoft.EntityFrameworkCore;

namespace GolfCoach.Api.Data;

public class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<Video> Videos => Set<Video>();
    public DbSet<Analysis> Analyses => Set<Analysis>();
    public DbSet<KeypointSet> KeypointSets => Set<KeypointSet>();
    public DbSet<Phase> Phases => Set<Phase>();
    public DbSet<Measurement> Measurements => Set<Measurement>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        // Ids are assigned in code (Guid.NewGuid()). Without ValueGeneratedNever, EF Core would treat a child
        // that has a preset Guid key and is attached through a navigation (e.g. analysis.KeypointSet = new ...)
        // as an EXISTING row and issue an UPDATE instead of an INSERT.
        foreach (var entityType in b.Model.GetEntityTypes())
            b.Entity(entityType.ClrType).Property("Id").ValueGeneratedNever();

        b.Entity<Video>(e =>
        {
            e.Property(x => x.OriginalFileName).HasMaxLength(255);
            e.Property(x => x.StoredPath).HasMaxLength(400);
            e.Property(x => x.Club).HasMaxLength(60);
            e.Property(x => x.Orientation).HasMaxLength(20);
            e.Property(x => x.CameraAngle).HasConversion<string>().HasMaxLength(20);
            e.Property(x => x.Handedness).HasConversion<string>().HasMaxLength(10);
        });

        b.Entity<Analysis>(e =>
        {
            e.HasOne(x => x.Video).WithMany(v => v.Analyses).HasForeignKey(x => x.VideoId)
                .OnDelete(DeleteBehavior.Cascade);
            e.Property(x => x.Status).HasConversion<string>().HasMaxLength(20);
            e.Property(x => x.Stage).HasMaxLength(100);
            e.Property(x => x.Error).HasMaxLength(2000);
            e.Property(x => x.PipelineVersion).HasMaxLength(40);
            e.Property(x => x.PoseModel).HasMaxLength(120);
            e.Property(x => x.QualityJson).HasColumnType("jsonb");
            e.Property(x => x.SwingJson).HasColumnType("jsonb");
            e.HasIndex(x => x.CreatedAt);
            e.HasIndex(x => x.Status);
        });

        b.Entity<KeypointSet>(e =>
        {
            e.HasOne(x => x.Analysis).WithOne(a => a.KeypointSet).HasForeignKey<KeypointSet>(x => x.AnalysisId)
                .OnDelete(DeleteBehavior.Cascade);
            e.HasIndex(x => x.AnalysisId).IsUnique();
            e.Property(x => x.FilePath).HasMaxLength(400);
            e.Property(x => x.DataFormat).HasMaxLength(60);
        });

        b.Entity<Phase>(e =>
        {
            e.HasOne(x => x.Analysis).WithMany(a => a.Phases).HasForeignKey(x => x.AnalysisId)
                .OnDelete(DeleteBehavior.Cascade);
            e.Property(x => x.Name).HasMaxLength(40);
            e.Property(x => x.DetectionMethod).HasMaxLength(60);
            e.HasIndex(x => x.AnalysisId);
        });

        b.Entity<Measurement>(e =>
        {
            e.HasOne(x => x.Analysis).WithMany(a => a.Measurements).HasForeignKey(x => x.AnalysisId)
                .OnDelete(DeleteBehavior.Cascade);
            e.Property(x => x.Name).HasMaxLength(80);
            e.Property(x => x.Phase).HasMaxLength(40);
            e.Property(x => x.Unit).HasMaxLength(20);
            e.Property(x => x.CameraAngle).HasConversion<string>().HasMaxLength(20);
            e.Property(x => x.Type).HasConversion<string>().HasMaxLength(20);
            e.HasIndex(x => x.AnalysisId);
        });
    }
}
