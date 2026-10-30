using System.Threading.Channels;

namespace GolfCoach.Api.Services;

/// <summary>
/// In-memory queue of analysis ids waiting for processing. A single worker drains it, because the CV
/// service processes one video at a time anyway. Unfinished analyses are re-queued from the database
/// on startup, so nothing is lost if the API restarts.
/// </summary>
public interface IAnalysisQueue
{
    void Enqueue(Guid analysisId);
    ChannelReader<Guid> Reader { get; }
}

public sealed class AnalysisQueue : IAnalysisQueue
{
    private readonly Channel<Guid> _channel =
        Channel.CreateUnbounded<Guid>(new UnboundedChannelOptions { SingleReader = true });

    public void Enqueue(Guid analysisId) => _channel.Writer.TryWrite(analysisId);

    public ChannelReader<Guid> Reader => _channel.Reader;
}
