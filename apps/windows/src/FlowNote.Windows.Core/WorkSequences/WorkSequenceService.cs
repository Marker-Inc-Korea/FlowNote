using FlowNote.Windows.Core.Storage;
using Microsoft.Data.Sqlite;

namespace FlowNote.Windows.Core.WorkSequences;

public sealed class WorkSequenceService(FlowNoteLocalDatabase database)
{
    public static readonly IReadOnlyList<string> AllowedItemStatuses =
    [
        "WAITING",
        "IN_PROGRESS",
        "HOLD",
        "COMPLETED"
    ];

    public WorkSequenceBoardRecord CreateBoard(
        string title,
        string createdBy,
        string? description = null,
        string? lineCode = null,
        DateTime? boardDate = null)
    {
        var now = DateTime.UtcNow;
        var boardId = $"wseq-board-{Guid.NewGuid():N}";
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO work_sequence_boards (
                board_id,
                title,
                description,
                line_code,
                board_date,
                status,
                created_by,
                created_at,
                updated_at
            )
            VALUES (
                $board_id,
                $title,
                $description,
                $line_code,
                $board_date,
                'ACTIVE',
                $created_by,
                $created_at,
                $updated_at
            );
            SELECT last_insert_rowid();
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        command.Parameters.AddWithValue("$title", Normalize(title, "Untitled board"));
        command.Parameters.AddWithValue("$description", DbValue(description));
        command.Parameters.AddWithValue("$line_code", DbValue(lineCode));
        command.Parameters.AddWithValue("$board_date", boardDate is null ? DBNull.Value : boardDate.Value.Date.ToString("yyyy-MM-dd"));
        command.Parameters.AddWithValue("$created_by", Normalize(createdBy, "system"));
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));
        command.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        command.ExecuteScalar();

        RecordChange(
            connection,
            boardId,
            null,
            "BOARD_CREATED",
            createdBy,
            null,
            title,
            "Initial board creation.",
            now);

        return GetBoard(boardId)
            ?? throw new InvalidOperationException($"Work sequence board not found after creation: {boardId}");
    }

    public WorkSequenceItemRecord AddItem(
        string boardId,
        string title,
        string createdBy,
        string? description = null,
        string? workOrderNo = null,
        string? documentId = null,
        string? assignedTo = null)
    {
        using var connection = database.OpenConnection();
        if (GetBoard(connection, boardId) is null)
        {
            throw new InvalidOperationException($"Work sequence board not found: {boardId}");
        }

        var now = DateTime.UtcNow;
        var itemId = $"wseq-item-{Guid.NewGuid():N}";
        var nextOrder = GetNextSortOrder(connection, boardId);
        using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO work_sequence_items (
                item_id,
                board_id,
                title,
                description,
                work_order_no,
                document_id,
                status,
                hold_reason,
                sort_order,
                assigned_to,
                created_by,
                created_at,
                updated_at
            )
            VALUES (
                $item_id,
                $board_id,
                $title,
                $description,
                $work_order_no,
                $document_id,
                'WAITING',
                NULL,
                $sort_order,
                $assigned_to,
                $created_by,
                $created_at,
                $updated_at
            );
            """;
        command.Parameters.AddWithValue("$item_id", itemId);
        command.Parameters.AddWithValue("$board_id", boardId);
        command.Parameters.AddWithValue("$title", Normalize(title, "Untitled item"));
        command.Parameters.AddWithValue("$description", DbValue(description));
        command.Parameters.AddWithValue("$work_order_no", DbValue(workOrderNo));
        command.Parameters.AddWithValue("$document_id", DbValue(documentId));
        command.Parameters.AddWithValue("$sort_order", nextOrder);
        command.Parameters.AddWithValue("$assigned_to", DbValue(assignedTo));
        command.Parameters.AddWithValue("$created_by", Normalize(createdBy, "system"));
        command.Parameters.AddWithValue("$created_at", now.ToString("O"));
        command.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        command.ExecuteNonQuery();

        TouchBoard(connection, boardId, now);
        RecordChange(connection, boardId, itemId, "ITEM_ADDED", createdBy, null, title, "Initial item creation.", now);

        return GetItems(boardId).Single(item => item.ItemId == itemId);
    }

    public IReadOnlyList<WorkSequenceBoardRecord> ListBoards()
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT board.id,
                   board.board_id,
                   board.title,
                   board.description,
                   board.line_code,
                   board.board_date,
                   board.status,
                   board.created_by,
                   board.created_at,
                   board.updated_at,
                   COUNT(item.id) AS item_count
            FROM work_sequence_boards AS board
            LEFT JOIN work_sequence_items AS item ON item.board_id = board.board_id
            GROUP BY board.id
            ORDER BY board.updated_at DESC, board.id DESC;
            """;
        using var reader = command.ExecuteReader();
        var records = new List<WorkSequenceBoardRecord>();
        while (reader.Read())
        {
            records.Add(ReadBoard(reader));
        }

        return records;
    }

    public WorkSequenceBoardRecord? GetBoard(string boardId)
    {
        using var connection = database.OpenConnection();
        return GetBoard(connection, boardId);
    }

    public IReadOnlyList<WorkSequenceItemRecord> GetItems(string boardId)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id,
                   item_id,
                   board_id,
                   title,
                   description,
                   work_order_no,
                   document_id,
                   status,
                   hold_reason,
                   sort_order,
                   assigned_to,
                   created_by,
                   created_at,
                   updated_at
            FROM work_sequence_items
            WHERE board_id = $board_id
            ORDER BY sort_order, id;
            """;
        command.Parameters.AddWithValue("$board_id", boardId);

        using var reader = command.ExecuteReader();
        var records = new List<WorkSequenceItemRecord>();
        while (reader.Read())
        {
            records.Add(ReadItem(reader));
        }

        return records;
    }

    public void ReorderItems(string boardId, IReadOnlyList<string> itemIds, string actorName, string? reason = null)
    {
        if (itemIds.Count == 0 || itemIds.Distinct(StringComparer.Ordinal).Count() != itemIds.Count)
        {
            throw new ArgumentException("Item ids must be unique.", nameof(itemIds));
        }

        using var connection = database.OpenConnection();
        var existing = GetItems(boardId).Select(item => item.ItemId).ToList();
        if (existing.Count != itemIds.Count || existing.OrderBy(item => item).SequenceEqual(itemIds.OrderBy(item => item)) is false)
        {
            throw new InvalidOperationException("Item ids must contain every item on the board exactly once.");
        }

        using var transaction = connection.BeginTransaction();
        for (var index = 0; index < existing.Count; index++)
        {
            using var temporary = connection.CreateCommand();
            temporary.Transaction = transaction;
            temporary.CommandText = """
                UPDATE work_sequence_items
                SET sort_order = $sort_order
                WHERE board_id = $board_id AND item_id = $item_id;
                """;
            temporary.Parameters.AddWithValue("$sort_order", -(index + 1));
            temporary.Parameters.AddWithValue("$board_id", boardId);
            temporary.Parameters.AddWithValue("$item_id", existing[index]);
            temporary.ExecuteNonQuery();
        }

        for (var index = 0; index < itemIds.Count; index++)
        {
            using var update = connection.CreateCommand();
            update.Transaction = transaction;
            update.CommandText = """
                UPDATE work_sequence_items
                SET sort_order = $sort_order,
                    updated_at = $updated_at
                WHERE board_id = $board_id AND item_id = $item_id;
                """;
            update.Parameters.AddWithValue("$sort_order", index + 1);
            update.Parameters.AddWithValue("$updated_at", DateTime.UtcNow.ToString("O"));
            update.Parameters.AddWithValue("$board_id", boardId);
            update.Parameters.AddWithValue("$item_id", itemIds[index]);
            update.ExecuteNonQuery();
        }

        var now = DateTime.UtcNow;
        TouchBoard(connection, boardId, now, transaction);
        RecordChange(
            connection,
            boardId,
            null,
            "ITEM_REORDERED",
            actorName,
            string.Join(",", existing),
            string.Join(",", itemIds),
            reason,
            now,
            transaction);
        var candidateId = RecordNotificationCandidate(
            connection,
            boardId,
            null,
            "work_sequence.reordered",
            actorName,
            ResolveReorderRecipient(connection, boardId, transaction),
            "Work sequence order changed.",
            transaction);
        DispatchWorkSequenceNotification(
            connection,
            boardId,
            null,
            candidateId,
            actorName,
            "Work sequence order changed.",
            now,
            transaction);
        transaction.Commit();
    }

    public WorkSequenceItemRecord UpdateItemStatus(
        string boardId,
        string itemId,
        string status,
        string actorName,
        string? reason = null,
        string? holdReason = null)
    {
        var normalizedStatus = NormalizeStatus(status);
        var normalizedHoldReason = normalizedStatus == "HOLD"
            ? NormalizeOptional(holdReason) ?? NormalizeOptional(reason)
            : null;
        var item = GetItems(boardId).FirstOrDefault(candidate => candidate.ItemId == itemId)
            ?? throw new InvalidOperationException($"Work sequence item not found: {itemId}");
        var statusChanged = !string.Equals(item.Status, normalizedStatus, StringComparison.Ordinal);
        var holdReasonChanged = !string.Equals(
            NormalizeOptional(item.HoldReason),
            normalizedHoldReason,
            StringComparison.Ordinal);
        if (!statusChanged && !holdReasonChanged)
        {
            return item;
        }

        using var connection = database.OpenConnection();
        var now = DateTime.UtcNow;
        using var update = connection.CreateCommand();
        update.CommandText = """
            UPDATE work_sequence_items
            SET status = $status,
                hold_reason = $hold_reason,
                updated_at = $updated_at
            WHERE board_id = $board_id AND item_id = $item_id;
            """;
        update.Parameters.AddWithValue("$status", normalizedStatus);
        update.Parameters.AddWithValue("$hold_reason", DbValue(normalizedHoldReason));
        update.Parameters.AddWithValue("$updated_at", now.ToString("O"));
        update.Parameters.AddWithValue("$board_id", boardId);
        update.Parameters.AddWithValue("$item_id", itemId);
        update.ExecuteNonQuery();

        TouchBoard(connection, boardId, now);
        if (statusChanged)
        {
            RecordChange(connection, boardId, itemId, "STATUS_CHANGED", actorName, item.Status, normalizedStatus, reason, now);
            var candidateId = RecordNotificationCandidate(
                connection,
                boardId,
                itemId,
                "work_sequence.status_changed",
                actorName,
                ResolveItemRecipient(connection, boardId, item),
                $"Work sequence item status changed: {item.Title} {item.Status} -> {normalizedStatus}.");
            DispatchWorkSequenceNotification(
                connection,
                boardId,
                itemId,
                candidateId,
                actorName,
                $"Work sequence item status changed: {item.Title} {item.Status} -> {normalizedStatus}.",
                now);
        }

        if (holdReasonChanged)
        {
            RecordChange(
                connection,
                boardId,
                itemId,
                "HOLD_REASON_CHANGED",
                actorName,
                item.HoldReason,
                normalizedHoldReason,
                reason,
                now);
            var candidateId = RecordNotificationCandidate(
                connection,
                boardId,
                itemId,
                "work_sequence.hold_reason_changed",
                actorName,
                ResolveItemRecipient(connection, boardId, item),
                $"Work sequence hold reason changed: {item.Title}.");
            DispatchWorkSequenceNotification(
                connection,
                boardId,
                itemId,
                candidateId,
                actorName,
                $"Work sequence hold reason changed: {item.Title}.",
                now);
        }

        return GetItems(boardId).Single(candidate => candidate.ItemId == itemId);
    }

    public IReadOnlyList<WorkSequenceHistoryRecord> ListHistory(string boardId, int limit = 100)
    {
        using var connection = database.OpenConnection();
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id,
                   change_id,
                   board_id,
                   item_id,
                   change_type,
                   actor_name,
                   before_value,
                   after_value,
                   change_reason,
                   created_at
            FROM work_sequence_change_history
            WHERE board_id = $board_id
            ORDER BY created_at DESC, id DESC
            LIMIT $limit;
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        command.Parameters.AddWithValue("$limit", limit);

        using var reader = command.ExecuteReader();
        var records = new List<WorkSequenceHistoryRecord>();
        while (reader.Read())
        {
            records.Add(new WorkSequenceHistoryRecord(
                reader.GetInt64(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.GetString(4),
                reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetString(8),
                DateTime.Parse(reader.GetString(9))));
        }

        return records;
    }

    private static WorkSequenceBoardRecord? GetBoard(SqliteConnection connection, string boardId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT board.id,
                   board.board_id,
                   board.title,
                   board.description,
                   board.line_code,
                   board.board_date,
                   board.status,
                   board.created_by,
                   board.created_at,
                   board.updated_at,
                   COUNT(item.id) AS item_count
            FROM work_sequence_boards AS board
            LEFT JOIN work_sequence_items AS item ON item.board_id = board.board_id
            WHERE board.board_id = $board_id
            GROUP BY board.id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadBoard(reader) : null;
    }

    private static int GetNextSortOrder(SqliteConnection connection, string boardId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT COALESCE(MAX(sort_order), 0) + 1
            FROM work_sequence_items
            WHERE board_id = $board_id;
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        return Convert.ToInt32(command.ExecuteScalar());
    }

    private static WorkSequenceBoardRecord ReadBoard(SqliteDataReader reader)
    {
        return new WorkSequenceBoardRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4),
            reader.IsDBNull(5) ? null : DateTime.Parse(reader.GetString(5)),
            reader.GetString(6),
            reader.GetString(7),
            DateTime.Parse(reader.GetString(8)),
            DateTime.Parse(reader.GetString(9)),
            reader.GetInt32(10));
    }

    private static WorkSequenceItemRecord ReadItem(SqliteDataReader reader)
    {
        return new WorkSequenceItemRecord(
            reader.GetInt64(0),
            reader.GetString(1),
            reader.GetString(2),
            reader.GetString(3),
            reader.IsDBNull(4) ? null : reader.GetString(4),
            reader.IsDBNull(5) ? null : reader.GetString(5),
            reader.IsDBNull(6) ? null : reader.GetString(6),
            reader.GetString(7),
            reader.IsDBNull(8) ? null : reader.GetString(8),
            reader.GetInt32(9),
            reader.IsDBNull(10) ? null : reader.GetString(10),
            reader.GetString(11),
            DateTime.Parse(reader.GetString(12)),
            DateTime.Parse(reader.GetString(13)));
    }

    private static void TouchBoard(
        SqliteConnection connection,
        string boardId,
        DateTime updatedAt,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE work_sequence_boards
            SET updated_at = $updated_at
            WHERE board_id = $board_id;
            """;
        command.Parameters.AddWithValue("$updated_at", updatedAt.ToString("O"));
        command.Parameters.AddWithValue("$board_id", boardId);
        command.ExecuteNonQuery();
    }

    private static void RecordChange(
        SqliteConnection connection,
        string boardId,
        string? itemId,
        string changeType,
        string? actorName,
        string? beforeValue,
        string? afterValue,
        string? reason,
        DateTime createdAt,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO work_sequence_change_history (
                change_id,
                board_id,
                item_id,
                change_type,
                actor_name,
                before_value,
                after_value,
                change_reason,
                created_at
            )
            VALUES (
                $change_id,
                $board_id,
                $item_id,
                $change_type,
                $actor_name,
                $before_value,
                $after_value,
                $change_reason,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$change_id", $"wseq-history-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$board_id", boardId);
        command.Parameters.AddWithValue("$item_id", DbValue(itemId));
        command.Parameters.AddWithValue("$change_type", changeType);
        command.Parameters.AddWithValue("$actor_name", Normalize(actorName, "system"));
        command.Parameters.AddWithValue("$before_value", DbValue(beforeValue));
        command.Parameters.AddWithValue("$after_value", DbValue(afterValue));
        command.Parameters.AddWithValue("$change_reason", DbValue(reason));
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();

        RecordActivityHistory(
            connection,
            $"work_sequence.{changeType.ToLowerInvariant()}",
            actorName,
            itemId is null ? "work_sequence_board" : "work_sequence_item",
            itemId ?? boardId,
            null,
            $"Work sequence change: {changeType}",
            createdAt,
            transaction);
    }

    private static string RecordNotificationCandidate(
        SqliteConnection connection,
        string boardId,
        string? itemId,
        string eventType,
        string? actorName,
        string? recipientName,
        string message,
        SqliteTransaction? transaction = null)
    {
        var candidateId = $"wseq-notify-{Guid.NewGuid():N}";
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO work_sequence_notification_candidates (
                candidate_id,
                board_id,
                item_id,
                event_type,
                actor_name,
                recipient_name,
                message,
                status,
                created_at
            )
            VALUES (
                $candidate_id,
                $board_id,
                $item_id,
                $event_type,
                $actor_name,
                $recipient_name,
                $message,
                'CANDIDATE',
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$candidate_id", candidateId);
        command.Parameters.AddWithValue("$board_id", boardId);
        command.Parameters.AddWithValue("$item_id", DbValue(itemId));
        command.Parameters.AddWithValue("$event_type", eventType);
        command.Parameters.AddWithValue("$actor_name", Normalize(actorName, "system"));
        command.Parameters.AddWithValue("$recipient_name", DbValue(recipientName));
        command.Parameters.AddWithValue("$message", Normalize(message, eventType));
        command.Parameters.AddWithValue("$created_at", DateTime.UtcNow.ToString("O"));
        command.ExecuteNonQuery();
        return candidateId;
    }

    private static string? ResolveReorderRecipient(
        SqliteConnection connection,
        string boardId,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT COALESCE(
                (
                    SELECT assigned_to
                    FROM work_sequence_items
                    WHERE board_id = $board_id
                      AND assigned_to IS NOT NULL
                      AND trim(assigned_to) <> ''
                    ORDER BY sort_order, id
                    LIMIT 1
                ),
                (
                    SELECT line_code
                    FROM work_sequence_boards
                    WHERE board_id = $board_id
                    LIMIT 1
                )
            );
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        return NormalizeOptional(command.ExecuteScalar() as string);
    }

    private static string? ResolveItemRecipient(
        SqliteConnection connection,
        string boardId,
        WorkSequenceItemRecord item)
    {
        if (!string.IsNullOrWhiteSpace(item.AssignedTo))
        {
            return item.AssignedTo.Trim();
        }

        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT line_code
            FROM work_sequence_boards
            WHERE board_id = $board_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$board_id", boardId);
        return NormalizeOptional(command.ExecuteScalar() as string);
    }

    private static void DispatchWorkSequenceNotification(
        SqliteConnection connection,
        string boardId,
        string? itemId,
        string candidateId,
        string? actorName,
        string message,
        DateTime createdAt,
        SqliteTransaction? transaction = null)
    {
        var target = LookupWorkSequenceTarget(connection, boardId, itemId, transaction);
        var recipientName = LookupCandidateRecipient(connection, candidateId, transaction)
            ?? NormalizeOptional(target.RecipientName);
        recipientName = ResolveNotificationRecipientName(connection, recipientName, transaction);
        if (recipientName is null || string.Equals(recipientName, Normalize(actorName, "system"), StringComparison.Ordinal))
        {
            UpdateCandidateStatus(connection, candidateId, "DISMISSED", null, transaction);
            return;
        }

        var notificationId = $"notification-{Guid.NewGuid():N}";
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO notifications (
                notification_id,
                notification_type,
                recipient_name,
                actor_name,
                document_id,
                document_title,
                target_type,
                target_id,
                target_title,
                source_candidate_id,
                message,
                is_read,
                created_at
            )
            VALUES (
                $notification_id,
                'work_sequence',
                $recipient_name,
                $actor_name,
                '',
                $target_title,
                $target_type,
                $target_id,
                $target_title,
                $source_candidate_id,
                $message,
                0,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$notification_id", notificationId);
        command.Parameters.AddWithValue("$recipient_name", recipientName);
        command.Parameters.AddWithValue("$actor_name", Normalize(actorName, "system"));
        command.Parameters.AddWithValue("$target_type", itemId is null ? "work_sequence_board" : "work_sequence_item");
        command.Parameters.AddWithValue("$target_id", itemId ?? boardId);
        command.Parameters.AddWithValue("$target_title", target.TargetTitle);
        command.Parameters.AddWithValue("$source_candidate_id", candidateId);
        command.Parameters.AddWithValue("$message", Normalize(message, "Work sequence changed."));
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();

        UpdateCandidateStatus(connection, candidateId, "SENT", notificationId, transaction);
        RecordActivityHistory(
            connection,
            "work_sequence.notification_sent",
            actorName,
            itemId is null ? "work_sequence_board" : "work_sequence_item",
            itemId ?? boardId,
            target.TargetTitle,
            $"Work sequence notification sent: {recipientName}",
            createdAt,
            transaction);
    }

    private static (string TargetTitle, string? RecipientName) LookupWorkSequenceTarget(
        SqliteConnection connection,
        string boardId,
        string? itemId,
        SqliteTransaction? transaction)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        if (itemId is null)
        {
            command.CommandText = """
                SELECT title, line_code
                FROM work_sequence_boards
                WHERE board_id = $board_id
                LIMIT 1;
                """;
            command.Parameters.AddWithValue("$board_id", boardId);
        }
        else
        {
            command.CommandText = """
                SELECT item.title, COALESCE(item.assigned_to, board.line_code)
                FROM work_sequence_items AS item
                JOIN work_sequence_boards AS board ON board.board_id = item.board_id
                WHERE item.board_id = $board_id AND item.item_id = $item_id
                LIMIT 1;
                """;
            command.Parameters.AddWithValue("$board_id", boardId);
            command.Parameters.AddWithValue("$item_id", itemId);
        }

        using var reader = command.ExecuteReader();
        if (!reader.Read())
        {
            return ("Work sequence", null);
        }

        return (
            reader.GetString(0),
            reader.IsDBNull(1) ? null : reader.GetString(1));
    }

    private static string? LookupCandidateRecipient(
        SqliteConnection connection,
        string candidateId,
        SqliteTransaction? transaction)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            SELECT recipient_name
            FROM work_sequence_notification_candidates
            WHERE candidate_id = $candidate_id
            LIMIT 1;
            """;
        command.Parameters.AddWithValue("$candidate_id", candidateId);
        return NormalizeOptional(command.ExecuteScalar() as string);
    }

    private static string? ResolveNotificationRecipientName(
        SqliteConnection connection,
        string? recipientHint,
        SqliteTransaction? transaction)
    {
        var normalizedHint = NormalizeOptional(recipientHint);
        if (normalizedHint is null)
        {
            return null;
        }

        using (var user = connection.CreateCommand())
        {
            user.Transaction = transaction;
            user.CommandText = """
                SELECT display_name
                FROM user_accounts
                WHERE user_id = $recipient
                   OR login_id = $recipient
                   OR display_name = $recipient
                LIMIT 1;
                """;
            user.Parameters.AddWithValue("$recipient", normalizedHint);
            if (NormalizeOptional(user.ExecuteScalar() as string) is { } displayName)
            {
                return displayName;
            }
        }

        using (var group = connection.CreateCommand())
        {
            group.Transaction = transaction;
            group.CommandText = """
                SELECT user.display_name
                FROM user_groups AS team
                JOIN user_accounts AS user ON user.user_id = team.leader_user_id
                WHERE team.group_id = $recipient
                   OR team.group_code = $recipient
                   OR team.group_name = $recipient
                LIMIT 1;
                """;
            group.Parameters.AddWithValue("$recipient", normalizedHint);
            if (NormalizeOptional(group.ExecuteScalar() as string) is { } leaderName)
            {
                return leaderName;
            }
        }

        return normalizedHint;
    }

    private static void UpdateCandidateStatus(
        SqliteConnection connection,
        string candidateId,
        string status,
        string? notificationId,
        SqliteTransaction? transaction)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            UPDATE work_sequence_notification_candidates
            SET status = $status,
                notification_id = $notification_id
            WHERE candidate_id = $candidate_id;
            """;
        command.Parameters.AddWithValue("$status", status);
        command.Parameters.AddWithValue("$notification_id", DbValue(notificationId));
        command.Parameters.AddWithValue("$candidate_id", candidateId);
        command.ExecuteNonQuery();
    }

    private static void RecordActivityHistory(
        SqliteConnection connection,
        string eventType,
        string? actorName,
        string targetType,
        string? targetId,
        string? targetTitle,
        string message,
        DateTime createdAt,
        SqliteTransaction? transaction = null)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO activity_history (
                history_id,
                event_type,
                actor_name,
                target_type,
                target_id,
                target_title,
                message,
                created_at
            )
            VALUES (
                $history_id,
                $event_type,
                $actor_name,
                $target_type,
                $target_id,
                $target_title,
                $message,
                $created_at
            );
            """;
        command.Parameters.AddWithValue("$history_id", $"history-{Guid.NewGuid():N}");
        command.Parameters.AddWithValue("$event_type", Normalize(eventType, "unknown"));
        command.Parameters.AddWithValue("$actor_name", Normalize(actorName, "system"));
        command.Parameters.AddWithValue("$target_type", Normalize(targetType, "unknown"));
        command.Parameters.AddWithValue("$target_id", DbValue(targetId));
        command.Parameters.AddWithValue("$target_title", DbValue(targetTitle));
        command.Parameters.AddWithValue("$message", Normalize(message, eventType));
        command.Parameters.AddWithValue("$created_at", createdAt.ToString("O"));
        command.ExecuteNonQuery();
    }

    private static string NormalizeStatus(string status)
    {
        var normalized = Normalize(status, "WAITING").ToUpperInvariant();
        return AllowedItemStatuses.Contains(normalized)
            ? normalized
            : throw new ArgumentOutOfRangeException(nameof(status), "Unsupported work sequence status.");
    }

    private static string Normalize(string? value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
    }

    private static string? NormalizeOptional(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static object DbValue(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? DBNull.Value : value.Trim();
    }
}
