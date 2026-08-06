package com.flownote.fieldapp;

import android.os.Handler;
import android.os.Looper;
import android.widget.LinearLayout;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.time.LocalDate;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class WorkSequenceController implements WorkSequenceView.Listener, AutoCloseable {
    interface Listener {
        void onOpenDocument(String documentId, String versionId, String title);

        void onStartFieldComment(WorkSequenceSource source, String itemTitle);

        void onStartHandover(WorkSequenceSource source, String itemTitle);
    }

    private static final int PAGE_SIZE = 50;

    private final WorkSequenceView view;
    private final WorkSequenceSnapshotStore snapshots;
    private final Listener listener;
    private final LinearLayout contentArea;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private FlowNoteApiClient apiClient;
    private WorkSequenceScope scope;
    private JSONObject currentPage;
    private boolean loading;
    private int generation;

    WorkSequenceController(
            android.content.Context context,
            LinearLayout contentArea,
            Listener listener
    ) {
        this.listener = listener;
        this.contentArea = contentArea;
        snapshots = new WorkSequenceSnapshotStore(context);
        view = new WorkSequenceView(context, this);
    }

    void show(FlowNoteApiClient apiClient, WorkSequenceScope scope) {
        attach();
        resetIfScopeChanged(scope);
        this.apiClient = apiClient;
        this.scope = scope;
        if (!scope.isComplete()) {
            view.showError("로그인 scope를 확인할 수 없습니다. 다시 로그인하세요.", false);
            return;
        }
        view.bindScope(scope, snapshots.loadFilter(scope), LocalDate.now().toString());
        WorkSequenceSnapshotStore.Snapshot cached = snapshots.loadList(
                scope, System.currentTimeMillis()
        );
        if (cached != null && matchesCurrentFilter(cached.payload)) {
            currentPage = cached.payload;
            view.showList(cached.payload, true, cached.savedAt);
        }
        refresh(false);
    }

    void openByItem(FlowNoteApiClient apiClient, WorkSequenceScope scope, String itemId) {
        attach();
        resetIfScopeChanged(scope);
        this.apiClient = apiClient;
        this.scope = scope;
        if (!scope.isComplete()) {
            view.showError("알림의 작업순서를 열려면 승인 단말로 다시 로그인하세요.", false);
            return;
        }
        fetchBoard(null, itemId, null);
    }

    @Override
    public void onRefresh(String date, String lineCode, boolean archived) {
        if (scope == null || !scope.isComplete()) {
            view.showError("승인 단말 로그인 정보가 필요합니다.", currentPage != null);
            return;
        }
        snapshots.saveFilter(scope, date, lineCode, archived);
        refresh(false);
    }

    @Override
    public void onLoadMore() {
        refresh(true);
    }

    private void refresh(boolean append) {
        if (loading || apiClient == null || scope == null) {
            return;
        }
        String date = view.dateFilter();
        if (!date.matches("\\d{4}-\\d{2}-\\d{2}")) {
            view.showError("날짜를 YYYY-MM-DD 형식으로 입력하세요.", currentPage != null);
            return;
        }
        int offset = append && currentPage != null
                ? currentPage.optJSONArray("items").length() : 0;
        String line = view.lineFilter();
        String boardStatus = view.archivedFilter() ? "ARCHIVED" : "ACTIVE";
        FlowNoteApiClient requestClient = apiClient;
        WorkSequenceScope requestScope = scope;
        JSONObject basePage = currentPage;
        int requestGeneration = generation;
        loading = true;
        view.showLoading(append ? "다음 작업판을 불러오는 중..." : "현재 권한의 작업판을 확인하는 중...");
        executor.execute(() -> {
            try {
                JSONObject response = requestClient.listWorkSequenceFieldBoards(
                        date, line, boardStatus, offset, PAGE_SIZE
                );
                requireMatchingScope(requestScope, response);
                response.put("filter_date", date);
                response.put("filter_line", line);
                response.put("filter_status", boardStatus);
                JSONObject merged = append ? mergePage(basePage, response) : response;
                long savedAt = System.currentTimeMillis();
                snapshots.saveList(requestScope, merged, savedAt);
                mainHandler.post(() -> {
                    if (!isActive(requestGeneration, requestScope)) {
                        return;
                    }
                    currentPage = merged;
                    loading = false;
                    view.showList(merged, false, savedAt);
                });
            } catch (Exception exc) {
                mainHandler.post(() -> {
                    if (!isActive(requestGeneration, requestScope)) {
                        return;
                    }
                    loading = false;
                    view.showError(
                            "작업판 갱신 실패: " + UserErrorMessage.from(exc), currentPage != null
                    );
                });
            }
        });
    }

    @Override
    public void onOpenBoard(String boardId, int revision) {
        WorkSequenceSnapshotStore.Snapshot cached = snapshots.loadBoard(
                scope, boardId, System.currentTimeMillis()
        );
        if (cached != null) {
            view.showBoard(cached.payload, true, cached.savedAt);
        }
        fetchBoard(boardId, null, revision);
    }

    private void fetchBoard(String boardId, String itemId, Integer expectedRevision) {
        if (loading || apiClient == null) {
            return;
        }
        FlowNoteApiClient requestClient = apiClient;
        WorkSequenceScope requestScope = scope;
        int requestGeneration = generation;
        loading = true;
        view.showLoading("작업순서 권한과 revision을 다시 확인하는 중...");
        executor.execute(() -> {
            try {
                JSONObject board = itemId == null
                        ? requestClient.getWorkSequenceFieldBoard(boardId, expectedRevision)
                        : requestClient.getWorkSequenceFieldItem(itemId, expectedRevision);
                requireMatchingScope(requestScope, board);
                long savedAt = System.currentTimeMillis();
                snapshots.saveBoard(requestScope, board.getString("board_id"), board, savedAt);
                mainHandler.post(() -> {
                    if (!isActive(requestGeneration, requestScope)) {
                        return;
                    }
                    loading = false;
                    view.showBoard(board, false, savedAt);
                });
            } catch (Exception exc) {
                mainHandler.post(() -> {
                    if (!isActive(requestGeneration, requestScope)) {
                        return;
                    }
                    loading = false;
                    view.showError(
                            "작업순서 상세 조회 실패: " + UserErrorMessage.from(exc), boardId != null
                    );
                });
            }
        });
    }

    @Override
    public void onOpenDocument(String documentId, String versionId, String title) {
        listener.onOpenDocument(documentId, versionId, title);
    }

    @Override
    public void onStartFieldComment(WorkSequenceSource source, String itemTitle) {
        listener.onStartFieldComment(source, itemTitle);
    }

    @Override
    public void onStartHandover(WorkSequenceSource source, String itemTitle) {
        listener.onStartHandover(source, itemTitle);
    }

    private boolean matchesCurrentFilter(JSONObject payload) {
        return view.dateFilter().equals(payload.optString("filter_date"))
                && view.lineFilter().equals(payload.optString("filter_line"))
                && (view.archivedFilter() ? "ARCHIVED" : "ACTIVE")
                .equals(payload.optString("filter_status"));
    }

    private static JSONObject mergePage(JSONObject current, JSONObject next) throws JSONException {
        if (current == null) {
            return next;
        }
        JSONObject merged = new JSONObject(current.toString());
        JSONArray target = merged.getJSONArray("items");
        JSONArray incoming = next.getJSONArray("items");
        for (int index = 0; index < incoming.length(); index++) {
            target.put(incoming.get(index));
        }
        merged.put("total", next.getInt("total"));
        merged.put("has_more", next.getBoolean("has_more"));
        merged.put("refreshed_at", next.optString("refreshed_at"));
        return merged;
    }

    private void attach() {
        contentArea.removeAllViews();
        if (view.getParent() instanceof LinearLayout) {
            ((LinearLayout) view.getParent()).removeView(view);
        }
        contentArea.addView(view, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        ));
    }

    void clearVisible() {
        generation++;
        loading = false;
        currentPage = null;
        scope = null;
        apiClient = null;
        contentArea.removeView(view);
    }

    private void resetIfScopeChanged(WorkSequenceScope nextScope) {
        if (scope == null || !scope.storageKey().equals(nextScope.storageKey())) {
            generation++;
            loading = false;
            currentPage = null;
            view.clearForScopeChange();
        }
    }

    private boolean isActive(int requestGeneration, WorkSequenceScope requestScope) {
        return generation == requestGeneration
                && scope != null
                && scope.storageKey().equals(requestScope.storageKey());
    }

    private static void requireMatchingScope(
            WorkSequenceScope requestScope,
            JSONObject response
    ) {
        if (!requestScope.matchesResponse(response)) {
            throw new IllegalStateException(
                    "서버가 반환한 작업순서 scope가 현재 로그인 scope와 다릅니다."
            );
        }
    }

    @Override
    public void close() {
        executor.shutdownNow();
    }
}
