using System.Text.Json;
using System.Text.Json.Serialization;
using GolfCoach.Api.Data;
using GolfCoach.Api.Endpoints;
using GolfCoach.Api.Services;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);

// ---- configuration -------------------------------------------------------------------------
builder.Services.Configure<StorageOptions>(builder.Configuration.GetSection("Storage"));
builder.Services.Configure<CvServiceOptions>(builder.Configuration.GetSection("CvService"));
builder.Services.Configure<UploadOptions>(builder.Configuration.GetSection("Upload"));

var maxUploadBytes = (builder.Configuration.GetSection("Upload").Get<UploadOptions>() ?? new UploadOptions()).MaxBytes;
builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = maxUploadBytes + 1024 * 1024);
builder.Services.Configure<FormOptions>(o => o.MultipartBodyLengthLimit = maxUploadBytes + 1024 * 1024);

// ---- JSON: camelCase properties (default) and snake_case enum values, e.g. "face_on" ---------
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower)));

// ---- services ------------------------------------------------------------------------------
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseNpgsql(builder.Configuration.GetConnectionString("Default")
                ?? throw new InvalidOperationException("ConnectionStrings:Default is not configured.")));

builder.Services.AddSingleton<StoragePaths>();
builder.Services.AddSingleton<IAnalysisQueue, AnalysisQueue>();
builder.Services.AddHttpClient<ICvServiceClient, CvServiceClient>(http => http.Timeout = TimeSpan.FromSeconds(30));
builder.Services.AddHostedService<AnalysisWorker>();

var app = builder.Build();

app.Services.GetRequiredService<StoragePaths>().EnsureFolders();
await DatabaseInitializer.InitialiseAsync(app.Services, app.Logger);

app.MapHealthEndpoints();
app.MapAnalysisEndpoints();

app.Run();
