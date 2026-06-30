namespace FlowNote.Windows.Core.ServerApi;

public sealed class FlowNoteServerAuthenticationException : InvalidOperationException
{
    public FlowNoteServerAuthenticationException(string message)
        : base(message)
    {
    }
}
