namespace FlowNote.Windows.Core.Auth;

public static class DocumentViewerPolicy
{
    public const string AutoCloseSecondsEnvironmentVariable = "FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS";
    public const int DefaultAutoCloseSeconds = 30;
    public const int MinimumAutoCloseSeconds = 5;
    public const int MaximumAutoCloseSeconds = 3600;

    public static TimeSpan ResolveAutoCloseDelay()
    {
        var configuredValue = Environment.GetEnvironmentVariable(AutoCloseSecondsEnvironmentVariable);
        if (!int.TryParse(configuredValue, out var seconds))
        {
            seconds = DefaultAutoCloseSeconds;
        }

        return NormalizeAutoCloseDelay(TimeSpan.FromSeconds(seconds));
    }

    public static TimeSpan NormalizeAutoCloseDelay(TimeSpan delay)
    {
        if (delay.TotalSeconds < MinimumAutoCloseSeconds)
        {
            return TimeSpan.FromSeconds(DefaultAutoCloseSeconds);
        }

        if (delay.TotalSeconds > MaximumAutoCloseSeconds)
        {
            return TimeSpan.FromSeconds(MaximumAutoCloseSeconds);
        }

        return delay;
    }
}
