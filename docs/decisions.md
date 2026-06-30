# FlowNote 설계 결정 요약

## 2026-06-30. WPF administrator file watch candidates

- WPF file watch is a local native feature based on `FileSystemWatcher`, not a server-side watcher.
- File watch is limited to administrator-level roles: `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`.
- `line-foreman`, `team-lead`, `team-member`, and `viewer` cannot open or run file watch even if some of them can register documents.
- A changed file is stored first as a `file_watch_candidates` row with `PENDING` status. It is not uploaded or made a new version automatically.
- Confirmation requires a target document, version label, and non-empty change reason. The file is then copied into local `Files/Uploads/yyyy-MM-dd/` storage and added as a new `document_versions` row.
- Candidate creation, confirmation, and ignore actions are recorded in `activity_history` as `file_watch.candidate_created`, `file_watch.candidate_confirmed`, and `file_watch.candidate_ignored`.
- Server synchronization for locally confirmed watched-file versions remains a follow-up policy item.

## 2026-06-30. Server-stored auth sessions for token refresh and revocation

- FastAPI auth now uses HMAC Bearer access tokens plus the `auth_sessions` table.
- Login creates an active server session and returns access and refresh tokens.
- Refresh rotates the access token ID and refresh token hash in the same session; old access and refresh tokens are rejected.
- Logout marks the current session as `REVOKED`; protected APIs reject revoked sessions with `401`.
- WPF does not silently auto-refresh yet. When document, FieldNote, attachment, or access-log sync receives `401`, the local save remains, the sync queue row is marked failed, and the user-facing status tells the user to sign in again.
- Development defaults such as `admin / 1234`, fixed WPF test passwords, and the default token secret remain local development values only and must be replaced for operational deployment.

이 문서는 FlowNote의 제품 방향과 구현 기준을 한 곳에 모은 결정 기록이다. 현재 코드와 맞지 않는 과거 표현은 제거하고, 구현된 범위와 후속 범위를 구분한다.

## 2026-06-29. WPF 로컬 우선 저장과 서버 동기화 큐

- Windows WPF 앱은 서버 연결 여부와 관계없이 로컬 SQLite 저장을 먼저 성공시킨다.
- 문서, FieldNote, FieldNote 첨부, 문서 접근 로그는 서버 전송 후보를 `server_sync_queue`에 남긴다.
- 서버 URL이 없거나 전송에 실패해도 로컬 저장을 되돌리지 않는다.
- 실패 사유는 `server_sync_queue.last_error`와 `activity_history`의 `server_sync.failed`에 남긴다.
- 재시도 성공 시 원천 테이블의 서버 ID/`synced_at` 컬럼과 `server_id_mappings`를 갱신한다.
- `server_sync_queue.status`는 `PENDING`, `FAILED`, `SYNCED`를 사용하고, `attempt_count`, `last_attempt_at`, `last_error`, `synced_at`으로 재시도 관측성을 유지한다.
- idempotency key는 문서 `wpf:document:{localDocumentId}:v1`, FieldNote `wpf:field-note:{noteId}`, FieldNote 첨부 `wpf:field-note-attachment:{attachmentId}`, 접근 로그 `wpf:access-log:{localAccessLogId}:{register_access_log_*}` 형식으로 생성한다.
- FastAPI는 문서 등록, FieldNote 등록, 문서 접근 로그 등록에서 선택 `idempotencyKey`를 받는다. 같은 키가 이미 있으면 새 행을 만들지 않고 기존 응답을 반환한다.
- FieldNote 첨부 API는 아직 서버 idempotency key를 받지 않는다. 현재는 WPF 로컬 큐의 고유 키와 `server_attachment_id`/`synced_at` 확인으로 중복 전송을 막고, 서버 첨부 idempotency는 후속 확장 대상으로 둔다.
- WPF 재시도는 원천 테이블에 서버 ID와 `synced_at`이 이미 있으면 네트워크 호출 전에 큐 행을 `SYNCED`로 정리하고 `activity_history.server_sync.skipped_already_synced`를 남긴다.

## 2026-06-29. 작업순서 폴더와 운영용 작업순서판 분리

- WPF 기본 폴더 `작업순서`는 작업 관련 파일을 보관하는 문서 구조로 유지한다.
- 운영 중 현재 실행 순서와 상태를 보여주는 데이터는 `work_sequence_boards`, `work_sequence_items`, `work_sequence_change_history`에 별도로 저장한다.
- 작업순서 항목 상태는 1차 구현에서 `WAITING`, `IN_PROGRESS`, `HOLD`, `COMPLETED`로 제한한다.
- 순서 변경, 상태 변경, 보류 사유 변경은 변경 이력과 알림 이벤트 후보로 남긴다.
- WPF는 관리자 편집 화면과 현장 TV 읽기 화면을 제공하고, FastAPI는 생성/항목 추가/정렬/상태 변경/이력 조회 API를 제공한다.

## 2026-06-30. 작업순서 알림 후보를 알림함 확인 흐름에 연결

- WPF 로컬 앱은 작업순서 순서 변경, 상태 변경, `HOLD` 보류 사유 변경 시 `work_sequence_notification_candidates`를 만들고 기존 `notifications` 알림함에 `notification_type=work_sequence` 알림을 생성한다.
- 작업순서 알림 대상은 항목 `assigned_to`를 우선 사용하고, 없으면 보드 `line_code`를 사용한다. 순서 변경은 보드 라인 또는 항목 담당 힌트를 대상으로 삼는다.
- WPF 로컬은 대상 힌트가 사용자 ID, 로그인 ID, 표시 이름이면 해당 사용자 표시 이름으로, 작업그룹 ID/코드/이름이면 그룹 리더 표시 이름으로 해석한다.
- 수신자가 없거나 수행자 자신에게 가는 알림은 후보를 `DISMISSED`로 전환한다. 알림 생성 성공 시 후보는 `SENT`가 된다.
- 알림함에서 작업순서 알림을 읽으면 `activity_history`에 `work_sequence.notification_read`를 남긴다.
- FastAPI는 작업순서 알림 후보 조회와 `CANDIDATE`, `SENT`, `DISMISSED` 상태 전환 API를 제공한다.

## 2026-06-29. 공개 버전은 명시적으로 지정

- 문서 업로드와 새 버전 등록은 자동으로 현장 공개 버전이 되지 않는다.
- `Document.latest_version_id`와 `Document.published_version_id`를 분리한다.
- 특정 버전을 공개하려면 `POST /api/v1/documents/{documentId}/versions/{versionId}/publish`를 호출한다.
- 공개 처리 시 대상 버전은 `version_status=PUBLISHED`, `is_published=true`가 되고 문서 상태는 `PUBLISHED`가 된다.
- 최신 작업 버전은 계속 `WORKING` 또는 `IN_REVIEW` 상태일 수 있다.

## 2026-06-29. MVP 인증과 role 기반 권한

- FastAPI 서버는 MVP 단계에서 HMAC 서명 Bearer access token을 사용한다.
- 토큰 서명 비밀값은 `FLOWNOTE_ACCESS_TOKEN_SECRET`, 만료 시간은 `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`로 설정한다.
- 운영 전에는 기본 개발용 비밀값과 `admin / 1234` 초기 비밀번호 정책을 반드시 교체한다.
- 서버 role 허용값은 `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`이다.
- 문서 쓰기, 태그 쓰기, 작업순서판 쓰기는 관리자 계열, 반장, 조장 이상에게 허용한다.
- `team-member`와 `viewer`는 FieldNote 작성 중심으로 제한한다.
- 문서 접근 로그 조회는 `admin`, `system-admin`으로 제한한다.

## 2026-06-24. FastAPI 문서 파일 로컬 저장 기준

- 문서 파일 바이너리는 SQLite에 직접 넣지 않고 서버 PC의 로컬 `storage/` 폴더에 저장한다.
- SQLite에는 `FileObject`, `Document`, `DocumentVersion`으로 원본 파일명, 확장자, MIME, 파일 계열, 크기, SHA-256 해시, 버전 번호, 변경 사유를 기록한다.
- 저장 키는 `documents/{document_id}/v{version_no}/{uuid}_{safe_filename}` 형식이다.
- 같은 원본 파일명이 반복 업로드되어도 버전별 파일을 덮어쓰지 않는다.

## 2026-06-24. FieldNote와 문서 버전 분리

- 현장 코멘트는 문서 파일 개정이 아니므로 신규 WPF 코멘트 저장 기본 경로는 `document_versions`가 아니라 `field_notes`이다.
- `document_versions`는 문서 파일 등록/개정 이력으로 유지한다.
- 기존 로컬 DB의 `document_versions.comment` 데이터는 초기화 시 `field_notes`로 백필한다.
- FieldNote는 원문 `raw_content`, 관리자 정리 `normalized_content`, 관리자 분석 `analysis_content`를 분리해 저장한다.
- 사진/파일 첨부는 `field_note_attachments`와 `file_objects` 또는 WPF 로컬 첨부 테이블에 분리 저장한다.

## 2026-06-26. 문서 열람 감사 로그

- 서버 URL이 없더라도 WPF 로컬 SQLite의 `document_view_logs`에 문서 열람 시작과 닫힘을 먼저 기록한다.
- 문서 보기 창이 열릴 때 문서 ID, 버전 번호, 사용자명, 열람 시작 시각을 저장한다.
- 창이 닫힐 때 닫힘 시각과 닫힘 사유를 같은 행에 갱신한다.
- 개발 검증용 자동 닫힘은 `auto_closed`로 기록한다.
- 서버 문서 ID와 버전 ID가 매핑되면 접근 로그를 FastAPI `POST /api/v1/documents/{documentId}/access-logs`로 전송한다.

## 2026-06-27. WPF 공통 로컬 SQLite 경로

- Windows WPF 앱과 Windows 스모크 테스트는 기본적으로 저장소 루트의 `data/local/flownote.local.sqlite`를 함께 사용한다.
- `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 지정되면 해당 위치를 우선 사용한다.
- 테스트마다 임시 SQLite를 만들지 않고 공통 DB에 기록과 이력을 누적한다.
- 업로드 파일, 렌더링 결과, 테스트 로그 같은 SQLite 외 산출물은 Git 추적 대상에서 제외한다.

## 제품 범위 결정

- FlowNote는 생산공장 문서와 현장 지식을 함께 관리한다.
- 단순 DMS나 순수 KMS 한쪽으로 치우치지 않는다.
- 초기 목표는 문서, 버전, 현장 코멘트, 사진 기록, 작업순서, 작업내역을 축적하는 것이다.
- AI 검색, 작업 조언, 보고서 초안은 축적 데이터의 후속 활용 계층이다.
- FlowNote는 MES/ERP를 대체하지 않는다. 기존 시스템은 후속 연동 대상으로 다룬다.

## 기술 방향 결정

- Backend는 Python FastAPI를 기준으로 한다.
- Client는 Windows WPF 기반 설치형 네이티브 앱 하나를 기준으로 한다.
- 운영 사용자는 일반 브라우저가 아니라 승인된 Windows 클라이언트로 접근한다.
- 메타데이터 DB는 SQLite를 우선 사용하고, 규모가 커지면 PostgreSQL로 확장한다.
- 파일은 서버 PC의 로컬 `storage/` 폴더에 저장한다.
- 배포는 서버 PC 1대와 클라이언트 설치파일 배포를 기본으로 한다.

## 문서 구조와 태그 결정

- 문서 구조는 고객이 결정한다.
- 트리 구조나 현장 용어의 BOM 문서 구조는 가능한 예시일 뿐 기본 강제 구조가 아니다.
- 초기 작업지시 구조는 관리자가 직접 입력한다.
- MES/ERP 연동이 추가되면 외부 원본 ID를 고객 정의 구조와 작업내역에 매핑한다.
- 문서 구조로 표현되지 않는 관계는 설비, 품목, 공정, 오류 유형, 라인, 위치 같은 태그로 보완한다.

## 현장 코멘트와 보고서 결정

- FieldNote는 원천 이력으로 보존한다.
- 짧은 코멘트, 신호등식 기록, 정형 문구, 관리자 대리 입력을 초기 입력 방식으로 둔다.
- 사진 첨부와 작업일지 사진은 현장 기록의 원천 데이터로 본다.
- 현장 코멘트는 관리자 분석과 보고서 문서화 과정을 거쳐 의사결정 가능한 정제 데이터로 발전시킨다.
- 최종 보고서는 다시 문서로 저장하고 원천 FieldNote, 작업내역, 관련 문서와 추적 가능하게 연결한다.

## 현장 의견 수용 기준

- 수용: 사진 기록, 짧은 코멘트, 인수인계, 작업순서판, 현장 공개 문서 열람 개선
- 검토: NFC/사원카드 로그인, OCR, 음성 입력, 앱 알림 제한, 기존 문서 대장 파싱
- 제외: 메신저 전체 기능, 개인 메신저 수집, GPS 추적, 근태 관리, MES/ERP 대체, 개인 휴대폰 기본 배포

## 보안과 배포 결정

- 고객 문서는 사내 서버형 운영을 우선한다.
- 클라우드나 외부 접근은 별도 협의가 필요한 후속 선택지이다.
- 로그인과 role 기반 권한을 적용한다.
- 다운로드 차단과 운영용 뷰어 자동 닫힘은 Windows WPF 클라이언트와 서버 감사 로그를 함께 사용해 강화한다.
- 문서 다운로드 권한은 문서 등록 권한보다 좁게 둔다. `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`만 controlled copy를 허용하고, `line-foreman`, `team-lead`, `team-member`, `viewer`는 차단한다.
- WPF 뷰어 자동 닫힘 기본값은 30초이며 `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`로 조정한다. 다운로드 차단은 `download_blocked`로 로컬 감사 로그와 서버 접근 로그 동기화 큐에 남긴다.
- FlowNote는 개인 감시 도구가 아니며, 개인 위치 추적이나 개인 메신저 수집을 하지 않는다.

