using System.Net;
using System.Text;
using GolfCoach.Api.Services;
using Microsoft.Extensions.Options;
using Xunit;

namespace GolfCoach.Api.Tests;

/// <summary>The native CV service is used when healthy; the one in Docker is the backup.</summary>
public class CvServiceRoutingTests
{
    private const string Native = "native.test", Docker = "docker.test";
    private const string Job = """{"job_id":"j","analysis_id":"a","status":"queued","progress":0,"stage":"Queued"}""";
    private static readonly CvJobRequest Request = new("a", "v", "k", "face_on", "right");

    private sealed class FakeServices(params string[] down) : HttpMessageHandler
    {
        public readonly List<string> Calls = [];
        public string NativeHealth = "ok";
        public HashSet<string> Down = [.. down];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var host = request.RequestUri!.Host;
            var path = request.RequestUri.AbsolutePath;
            Calls.Add($"{host}{path}");
            if (Down.Contains(host)) throw new HttpRequestException("connection refused");
            var status = host == Native ? NativeHealth : "ok";
            var body = path == "/health"
                ? $$"""{"status":"{{status}}","pipeline_version":"1","pose_model_present":true,"data_dir_present":true}"""
                : Job;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json"),
            });
        }
    }

    private static CvServiceClient Client(FakeServices services, bool withNative = true) =>
        new(new HttpClient(services), Options.Create(new CvServiceOptions
        {
            BaseUrl = $"http://{Docker}",
            NativeUrl = withNative ? $"http://{Native}:8001" : null,
        }));

    [Fact]
    public async Task Job_goes_to_the_native_service_and_is_polled_there()
    {
        var services = new FakeServices();
        var client = Client(services);

        await client.SubmitJobAsync(Request, default);
        await client.GetJobAsync("j", default);

        Assert.Contains($"{Native}/jobs", services.Calls);
        Assert.Contains($"{Native}/jobs/j", services.Calls);
        Assert.DoesNotContain(services.Calls, c => c.StartsWith(Docker));
    }

    [Fact]
    public async Task Job_goes_to_docker_when_the_native_service_is_down()
    {
        var services = new FakeServices(Native);
        var client = Client(services);

        await client.SubmitJobAsync(Request, default);
        await client.GetJobAsync("j", default);

        Assert.Contains($"{Docker}/jobs", services.Calls);
        Assert.Contains($"{Docker}/jobs/j", services.Calls);
    }

    [Fact]
    public async Task Job_goes_to_docker_when_the_native_service_is_unhealthy()
    {
        var services = new FakeServices { NativeHealth = "degraded" };

        await Client(services).SubmitJobAsync(Request, default);

        Assert.Contains($"{Docker}/jobs", services.Calls);
        Assert.DoesNotContain($"{Native}/jobs", services.Calls);
    }

    [Fact]
    public async Task Native_service_dying_mid_job_moves_the_job_to_docker()
    {
        var services = new FakeServices();
        var client = Client(services);
        await client.SubmitJobAsync(Request, default);

        services.Down.Add(Native);
        Assert.Null(await client.GetJobAsync("j", default)); // null = "lost": the worker resubmits

        await client.SubmitJobAsync(Request, default);
        Assert.Contains($"{Docker}/jobs", services.Calls);
    }

    [Fact]
    public async Task Docker_being_unreachable_stays_a_transient_error()
    {
        var services = new FakeServices(Docker);
        var client = Client(services, withNative: false);

        await Assert.ThrowsAsync<HttpRequestException>(() => client.GetJobAsync("j", default));
    }
}
