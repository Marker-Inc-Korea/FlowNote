using FlowNote.Windows.Core.ServerApi;
using Xunit;

namespace FlowNote.Windows.Core.Tests;

public sealed class HandoverSupervisionSummaryTests
{
    [Fact]
    public void ReceiptSummarySeparatesUnconfirmedAndFollowUpRecipients()
    {
        var handover = new ServerHandoverResponse
        {
            Receipts =
            [
                new ServerHandoverReceiptResponse { ReceiptStatus = "UNREAD" },
                new ServerHandoverReceiptResponse { ReceiptStatus = "READ" },
                new ServerHandoverReceiptResponse { ReceiptStatus = "ACKNOWLEDGED" },
                new ServerHandoverReceiptResponse { ReceiptStatus = "FOLLOW_UP_REQUIRED" }
            ]
        };

        Assert.Equal(2, handover.UnconfirmedRecipientCount);
        Assert.Equal(1, handover.FollowUpRequiredCount);
        Assert.Equal("미확인 2명 / 후속 1명", handover.ReceiptSummary);
    }
}
