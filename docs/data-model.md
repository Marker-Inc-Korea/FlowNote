# FlowNote 데이터 모델

## 0. 데이터베이스 기준

### 0.0 현재 코드 기준 로컬 SQLite 모델

현재 실제 코드에서 사용하는 SQLite 모델은 Windows WPF 앱의 로컬 프로토타입 모델이다. DB 파일은 개발 실행 기준 저장소 루트의 `data/local/flownote.local.sqlite`를 우선 사용한다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 지정된 경우 그 위치를 우선 사용하고, 저장소 루트를 찾을 수 없는 배포 실행에서는 앱 실행 폴더의 `Data/flownote.local.sqlite`를 사용한다.

현재 구현 테이블은 다음과 같다.

| 테이블 | 현재 역할 |
| --- | --- |
| `user_accounts` | 로그인 계정. 기본 `admin / 1234`, 관리자 그룹 계정, 반장 3명 기준 작업조 테스트 계정을 저장 |
| `user_groups` | WPF 로컬 개발/스모크 테스트용 최소 그룹. 관리자 그룹과 반장별 작업조를 저장 |
| `document_folders` | 루트, 기본 폴더, 문서 분류 폴더, 날짜 하위 폴더를 저장 |
| `documents` | 문서 메타데이터, 로컬 파일 상대 경로, 상태, 최신 버전, 최신 코멘트 요약을 저장 |
| `document_versions` | 원본 등록 버전과 파일 개정 버전을 저장. 기존 코멘트 버전은 호환용으로 남아 있으나 신규 WPF 코멘트 저장 기본 경로는 아님 |
| `field_comments` | WPF 오프라인 현장 코멘트 최소 원천 이력. 문서 ID, 현재 문서 버전 번호, 입력 방식, 원문, 작성자, 동기화 상태 후보를 저장 |
| `field_comment_attachments` | WPF 오프라인 FieldComment 사진/파일 첨부 이력. 로컬 보존 경로, 원본 파일명, 확장자, 크기, SHA-256, 서버 첨부 ID 후보를 저장 |
| `document_view_logs` | WPF 로컬 문서 열람/차단 감사 로그. 문서 ID, 버전 번호, 사용자명, 열람 시작 시각, 닫힘 시각, 닫힘 사유(`window_closed`, `auto_closed`, `download_blocked`)를 저장 |
| `activity_history` | WPF 로컬 전체 이력. 사용자별 알림과 별개로 누가 어떤 문서/폴더/알림/열람 작업을 수행했는지 최신순 조회용으로 저장 |
| `file_watch_candidates` | WPF 로컬 관리자 파일 감시 후보. 감지 파일 경로, 파일명, 크기, 수정 시각, 연결 문서, 후보 상태(`PENDING`, `CONFIRMED`, `IGNORED`), 버전명, 변경 사유, 처리자를 저장 |
| `tag_definitions`, `document_tags` | WPF 로컬 문서 태그 사전과 문서-태그 연결. 문서 등록 시 입력 태그와 자동 태그를 저장 |
| `notifications` | 새 현장 코멘트 또는 기존 코멘트 버전 생성 시 문서 작성자/관련 작성자 대상 알림을 저장 |
| `work_sequence_boards`, `work_sequence_items` | WPF 로컬 작업순서판과 작업순서 항목. 파일 기반 `작업순서` 폴더 기록과 분리된 운영 보드 데이터를 저장 |
| `work_sequence_change_history` | WPF 로컬 작업순서 항목 추가, 순서 변경, 상태 변경 이력을 저장 |
| `work_sequence_notification_candidates` | WPF 로컬 작업순서 순서 변경과 상태 변경에 대한 알림 이벤트 후보를 저장 |
| `server_sync_queue` | WPF 로컬 문서, FieldComment, FieldComment 첨부, 접근 로그의 서버 전송 후보와 실패 사유, 재시도 상태, idempotency key, 서버 ID 결과를 저장 |
| `server_id_mappings` | 로컬 문서/버전/FieldComment/FieldComment 첨부/접근 로그와 서버 `document_id`, `version_id`, `comment_id`, `attachment_id`, `log_id` 매핑을 저장 |

현재 앱은 문서 등록 시 상태를 `WORKING`으로 저장한다. 문서 등록/파일 업로드와 새 로컬 버전은 자동 공개하지 않고, 관리자가 선택 문서의 최신 버전을 공개 처리해야 `documents.published_version_no`와 `document_versions.is_published`가 갱신된다. WPF 문서 목록은 최신 버전과 공개 버전을 따로 표시한다. 문서 등록/파일 업로드 시 태그 입력값과 기본 태그를 `tag_definitions`, `document_tags`에 저장하고 목록에서 표시한다. WPF 문서 보기 화면에서 새로 남기는 코멘트는 `field_comments`에 저장하고, 선택한 사진/파일은 `data/local/Files/FieldCommentAttachments/` 아래에 복사한 뒤 `field_comment_attachments`에 로컬 경로와 파일 메타데이터를 남긴다. `document_versions`는 문서 파일 개정 이력으로 유지하며, 파일 감시 확정 흐름의 변경 사유는 `comment`, 버전명은 `version_label`에 저장한다. 기존 DB에 `document_versions.comment`로 누적된 코멘트는 앱 초기화 시 `field_comments`로 백필한다. 관리자급 role은 WPF `File Watch` 창에서 감시 폴더를 시작할 수 있고, 변경 감지 파일은 즉시 업로드하지 않고 `file_watch_candidates`에 후보로 남긴 뒤 관리자가 변경 사유와 버전명을 입력할 때 기존 문서의 새 `document_versions` 행으로 확정한다. 후보 생성, 확정, 무시는 `activity_history`에 남긴다. 문서 보기 창은 열릴 때 `document_view_logs`에 열람 시작을 저장하고 닫힐 때 닫힘 시각과 사유를 갱신한다. 작업순서판은 `work_sequence_boards`, `work_sequence_items`, `work_sequence_change_history`에 별도 저장한다. 기존 `작업순서` 폴더의 파일 등록 흐름은 파일 기반 기록 보관이며, 새 작업순서판은 현재 실행 순서와 상태를 보여주는 운영 데이터이다. 순서 변경과 상태 변경은 작업순서 이력과 알림 이벤트 후보로 남기며 문서 버전이나 FieldComment로 섞지 않는다. 폴더 생성, 문서 등록, 문서 버전 증가, 문서 상태 변경, 문서 공개 처리, 현장 코멘트 등록, FieldComment 첨부 등록, 문서 열람 시작/종료, 알림 읽음 처리, 작업순서 변경 같은 로컬 변경/감사 이벤트는 `activity_history`에 수행자와 함께 저장하고 상단 `이력` 메뉴에서 사용자 필터 없이 조회한다. WPF 로그인 화면은 `FLOWNOTE_API_BASE_URL`이 설정된 경우 서버 `POST /api/v1/auth/login`을 먼저 호출하고, 성공 응답의 `user_id`, `username`, `role`, `display_name`, `access_token`, `expires_at`을 앱 로그인 결과로 사용한다. 서버 URL이 없거나 서버 로그인 호출이 실패하면 로컬 `user_accounts` 기반 로그인으로 처리한다. 서버 로그인에 성공한 경우 WPF 서버 API 클라이언트는 문서/FieldComment/FieldComment 첨부/접근 로그/작업순서판 요청에 Bearer 인증 헤더를 붙인다. WPF 서버 API 클라이언트는 서버 문서 새 버전 등록, 공개 전환, 공개 버전 조회 응답도 처리한다. 로컬 FieldComment를 서버 `field_comments` 등록 요청으로 변환할 수 있지만, 로컬 DB의 `document_version_no`는 서버 등록 시 직접 전송하지 않고 서버의 `document_versions.version_id`가 확인된 경우 `documentVersionId`로 전달한다. 문서/FieldComment/FieldComment 첨부/접근 로그 서버 전송 후보는 `server_sync_queue`에 남기며, 서버 URL이 없거나 전송이 실패해도 로컬 저장을 성공으로 유지하고 실패 사유를 `server_sync_queue.last_error`와 `activity_history.server_sync.failed`에 기록한다. `server_sync_queue.status`는 `PENDING`, `FAILED`, `SYNCED`로 표시하고, `attempt_count`, `last_attempt_at`, `last_error`, `synced_at`, 서버 ID 컬럼으로 재시도 횟수와 마지막 오류, 성공 시각을 확인한다. 재시도 시작은 `activity_history.server_sync.retry_attempted`, 이미 `synced_at`/서버 ID가 있어 네트워크 호출을 생략한 경우는 `server_sync.skipped_already_synced`, 전체 재시도 결과는 `server_sync.retry_completed` 또는 `server_sync.retry_completed_with_failures`로 보존한다. 재시도 성공 시 `documents.server_document_id`, `documents.server_version_id`, `documents.synced_at`, `document_versions.server_version_id`, `field_comments.server_comment_id`, `field_comments.synced_at`, `field_comment_attachments.server_attachment_id`, `field_comment_attachments.synced_at`, `document_view_logs.server_start_log_id`, `document_view_logs.server_close_log_id`, `document_view_logs.synced_at`, `server_id_mappings`를 갱신한다. 중복 등록은 로컬 idempotency key, FastAPI 문서/FieldComment/접근 로그의 `idempotency_key`, 이미 기록된 `synced_at`/서버 ID를 기준으로 줄인다. 역할 테이블, 권한 테이블, 작업내역, 보고서, AI 로그, 서버 저장소용 `FileObject`는 아직 WPF 로컬 앱 코드에 구현되어 있지 않다. 아래 데이터 모델은 제품 목표와 서버 확장 초안이며 현재 코드 구현 완료를 뜻하지 않는다.

2026-06-30 기준 서버에는 수동 보고서 초안/승인/원천 연결/문서 저장 API가 구현되어 있고, WPF에는 로컬 FieldComment/문서/작업순서 이력 원천을 확인해 보고서 문서로 저장하는 최소 화면이 있다. 다만 WPF 보고서 전용 서버 동기화 큐는 아직 구현하지 않았다.

WPF 로컬 DB 초기화는 개발/스모크 테스트용으로 다음 그룹과 계정을 보장한다. 모든 계정의 비밀번호는 `1234`이며, 현재 단계에서는 role 값으로 문서 등록/파일 업로드/작업순서판 편집 같은 쓰기 기능을 제한한다. 문서 등록 가능 기준은 관리자 계열, 반장, 조장이고, 조원은 FieldComment 작성 중심으로 검증한다. 차장, 부장, 관리자 계정은 작업조가 아니라 `group-admin` 관리자 그룹에 둔다.

| group_id | group_name | group_type | leader_user_id |
| --- | --- | --- | --- |
| `group-admin` | 관리자 그룹 | `admin` |  |
| `group-line-a` | 반장 A 작업조 | `work_team` | `user-foreman-a` |
| `group-line-b` | 반장 B 작업조 | `work_team` | `user-foreman-b` |
| `group-line-c` | 반장 C 작업조 | `work_team` | `user-foreman-c` |

| group_id | user_id | login_id | 표시명 | role | supervisor_user_id |
| --- | --- | --- | --- | --- | --- |
| `group-admin` | `user-admin` | `admin` | `Administrator` | `system-admin` |  |
| `group-admin` | `user-deputy` | `deputy` | `차장` | `assistant-manager` |  |
| `group-admin` | `user-depthead` | `depthead` | `부장` | `department-manager` |  |
| `group-admin` | `user-manager` | `manager` | `관리자` | `document-admin` |  |
| `group-line-a` | `user-foreman-a` | `foreman-a` | `반장 A` | `line-foreman` |  |
| `group-line-a` | `user-lead-a1` | `lead-a1` | `조장 A-1` | `team-lead` | `user-foreman-a` |
| `group-line-a` | `user-member-a1` | `member-a1` | `조원 A-1` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a2` | `member-a2` | `조원 A-2` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a3` | `member-a3` | `조원 A-3` | `team-member` | `user-foreman-a` |
| `group-line-a` | `user-member-a4` | `member-a4` | `조원 A-4` | `team-member` | `user-foreman-a` |
| `group-line-b` | `user-foreman-b` | `foreman-b` | `반장 B` | `line-foreman` |  |
| `group-line-b` | `user-lead-b1` | `lead-b1` | `조장 B-1` | `team-lead` | `user-foreman-b` |
| `group-line-b` | `user-lead-b2` | `lead-b2` | `조장 B-2` | `team-lead` | `user-foreman-b` |
| `group-line-b` | `user-member-b1` | `member-b1` | `조원 B-1` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b2` | `member-b2` | `조원 B-2` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b3` | `member-b3` | `조원 B-3` | `team-member` | `user-foreman-b` |
| `group-line-b` | `user-member-b4` | `member-b4` | `조원 B-4` | `team-member` | `user-foreman-b` |
| `group-line-c` | `user-foreman-c` | `foreman-c` | `반장 C` | `line-foreman` |  |
| `group-line-c` | `user-lead-c1` | `lead-c1` | `조장 C-1` | `team-lead` | `user-foreman-c` |
| `group-line-c` | `user-member-c1` | `member-c1` | `조원 C-1` | `team-member` | `user-foreman-c` |
| `group-line-c` | `user-member-c2` | `member-c2` | `조원 C-2` | `team-member` | `user-foreman-c` |
| `group-line-c` | `user-member-c3` | `member-c3` | `조원 C-3` | `team-member` | `user-foreman-c` |

프로그램 테스트 기준에서는 문서 등록을 여러 ID로 확인하되, 문서 등록 가능 그룹은 조장 이상으로 둔다. 코멘트 등록은 ID 제한을 두지 않는다. 프로그램 테스트용 문서 파일은 사용자가 직접 화면에서 확인하는 언어가 맞아야 하므로 파일명과 표시 문구를 한글, 숫자, 영문만으로 구성하고 `???` 같은 깨진 문자가 포함된 파일은 테스트 기준에서 제외한다. 이 제한은 프로그램 테스트용 문서 파일에만 적용하며, 일반 문서 파일이나 MD 문서 작성 기준에는 적용하지 않는다. 서버 URL인 `FLOWNOTE_API_BASE_URL`이 없으면 로컬 SQLite 기준으로 검증하고, 서버 URL이 설정된 경우에만 FastAPI 연동 검증을 추가한다. 스모크 테스트를 포함한 프로그램 테스트는 공통 SQLite인 `data/local/flownote.local.sqlite`를 계속 사용하고, 매 실행 기록을 누적 보존한다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 지정된 경우 해당 위치의 공통 DB에 누적한다. 스모크 테스트는 사용자가 명시적으로 요청하지 않은 스모크/테스트 전용 업무 폴더를 앱 문서 구조에 만들지 않고, 현재 기본 폴더 체계와 그 규칙에서 파생된 분류/날짜 폴더 기준으로 진행한다. 알림 테스트는 누적된 전체 알림 개수를 제한하지 않고, 특정 notify 이벤트가 해당 문서와 수신자 기준으로 1건 생성되는지만 검증한다. 스모크 테스트는 항상 오늘 날짜의 `사진`과 `인수인계` 문서 등록을 포함하고, 날짜 폴더 생성, 문서 등록, 목록 조회를 확인한다. 과거 날짜 테스트는 이미 존재하는 `사진` 또는 `인수인계` 날짜 폴더와 그 안의 기존 문서를 랜덤하게 선택해 버전 증가만 검증하며, 과거 날짜 폴더나 과거 날짜 문서를 새로 만들지 않는다.

### 0.0.1 FastAPI 서버 SQLite 초기 모델

2026-06-24 기준 FastAPI 서버에는 SQLite 연결과 MVP 초기 테이블 생성 기준이 추가되었다. 서버 DB는 `services/api/app/db/models.py`의 SQLAlchemy 모델을 기준으로 하고, 앱 시작 시 `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다. 문서 등록 API는 `documents`, `document_versions`, `file_objects`를 함께 사용해 문서 메타데이터, 파일 저장 참조, 버전 번호, 변경 사유를 로컬에 저장한다.

2026-06-25 기준 서버 로그인 API는 `user_accounts`의 `username`, `password_hash`, `role`, `is_active`, `status`를 사용한다. 서버 DB 초기화 시 개발용 기본 관리자 계정 `admin / 1234`가 없으면 생성한다. 이 기본 계정은 로컬 개발과 MVP 검증용 기준이며, 운영 배포에서는 별도 초기 비밀번호 정책으로 교체해야 한다. 2026-06-30 기준 서버 로그인 API는 `auth_sessions`에 세션을 만들고 HMAC Bearer access token, refresh token, 각 만료 시각을 반환한다. access token에는 사용자 ID, 세션 ID, access token ID, 만료 시각이 들어가며, 서버는 토큰 서명뿐 아니라 `auth_sessions.status`, `access_token_id`, `revoked_at`, `access_expires_at`을 함께 검증한다. refresh API는 같은 세션의 access token ID와 refresh token hash를 회전하므로 이전 access token과 이전 refresh token은 재사용할 수 없다. logout API는 세션을 `REVOKED`로 바꾸며 이후 같은 토큰의 문서/FieldComment/FieldComment 첨부/문서 접근 로그 요청은 `401`을 반환한다. 같은 날짜 기준으로 서버 role 제약은 `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`를 허용한다. 문서 등록/버전 등록/태그 변경은 관리자 그룹, 반장, 조장 이상만 허용하고 조원은 FieldComment 등록과 첨부 등록 중심으로 제한한다. Windows WPF 로그인 화면은 `FLOWNOTE_API_BASE_URL`이 설정된 경우 서버 로그인 응답을 먼저 사용할 수 있고, 서버 URL이 없거나 호출이 실패하면 기존 로컬 SQLite 로그인을 유지한다. Windows WPF 서버 API 클라이언트는 서버 문서 등록/목록/버전 조회뿐 아니라 문서 버전에 연결된 서버 FieldComment 등록, FieldComment 첨부 등록/조회, 문서 접근 로그 등록/조회 응답까지 받을 수 있다. access token 만료 또는 세션 폐기 시 WPF는 서버 전송 후보를 실패 큐에 남기고 재로그인이 필요하다는 실패 사유를 `server_sync_queue.last_error`와 상태 메시지에 표시한다.

기본 개발 DB 경로는 `services/api/data/flownote.sqlite3`, 테스트 DB 경로는 `services/api/data/flownote.test.sqlite3`이다. Windows 앱과 Windows 스모크 테스트는 공통 DB인 `data/local/flownote.local.sqlite`를 함께 사용한다. 테스트 DB와 검증 기록은 누적 테스트 기록이므로 삭제하지 않고 보존한다. SQLite DB는 후속 테스트와 기능 추가의 근거 데이터로 사용할 수 있으므로 Git 추적 및 커밋 대상에 포함될 수 있다. 문서 등록 통합 테스트 샘플과 로그는 `services/api/data/test-artifacts/document-registration-2026-06-24/` 아래에 보존하고, 업로드 저장 파일은 `services/api/storage/document-registration-tests/` 아래에 보존한다.

현재 서버 초기 스키마 테이블은 다음과 같다.

| 테이블 | 현재 역할 |
| --- | --- |
| `schema_migrations` | 서버 DB 스키마 적용 버전 기록 |
| `user_accounts`, `roles`, `user_roles` | 로그인 계정과 역할 연결의 초기 기준 |
| `auth_sessions` | 서버 로그인 세션, access token ID, refresh token hash, 만료/폐기 상태 |
| `operator_profiles` | 실제 작업자, 작업그룹, 대리 등록 주체 추적 |
| `file_objects` | 서버 로컬 `storage/` 파일 참조 |
| `documents`, `document_versions` | 문서 메타데이터, 버전, 변경 사유, 공개/최신 구분. `documents.idempotency_key`는 WPF 로컬 등록 재시도 중복 방지에 사용 |
| `activity_history` | 문서 상태 변경, 문서 버전 상태 변경, 공개 처리 같은 서버 변경 이력 후보 |
| `tag_definitions`, `document_tags` | 설비, 품목, 공정, 오류 유형 등 태그 연결 |
| `terminal_devices` | 현장/관리자 단말기 등록 기준 |
| `field_comments`, `field_comment_attachments` | 현장 코멘트 원천 이력과 사진/첨부 연결. `field_comments.idempotency_key`는 WPF FieldComment 재시도 중복 방지에 사용 |
| `comment_templates` | 신호등식/정형 문구 입력 보조 |
| `work_records`, `work_record_versions` | 작업내역과 버전의 초기 기준 |
| `work_sequence_boards`, `work_sequence_items`, `work_sequence_change_history`, `work_sequence_notification_candidates` | 관리자 입력 기준 작업순서판, 항목, 순서/상태 변경 이력, 알림 이벤트 후보 |
| `reports`, `report_sources` | 관리자 보고서와 원천 데이터 추적 |
| `document_access_logs` | 문서 열람, 다운로드 차단, 뷰어 닫힘 등 감사 로그 기반. `idempotency_key`는 WPF 접근 로그 재시도 중복 방지에 사용 |

FlowNote의 메타데이터 DB는 SQLite를 우선 사용한다. 현장 규모나 동시성이 커지면 PostgreSQL로 확장한다.

파일 바이너리는 DB에 직접 저장하지 않고 서버 PC의 로컬 `storage/` 폴더에 저장한다. 현재 문서 업로드 저장 키는 `documents/{document_id}/v{version_no}/{uuid}_{safe_filename}` 형식을 사용한다. SQLite에는 문서 메타데이터, 파일 참조 정보, 버전, 변경 사유, 권한, 이력, 단말기, 현장 코멘트, 작업내역, AI 조언 로그를 저장한다.

FlowNote는 MES/ERP를 대체하지 않는다. 외부 시스템이 있는 경우 원본 업무 데이터는 해당 시스템에 두고, FlowNote는 외부 참조 ID와 매핑 정보를 저장해 문서, 현장 코멘트, 작업내역, 보고서와 연결한다.

## 0.1 회원과 권한 모델

### UserAccount

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| user_id | 외부 참조용 사용자 ID |
| username | 로그인 API에서 조회하는 사용자명. 서버 MVP에서는 고유값 |
| login_id | 로그인 ID |
| display_name | 표시명 |
| role | 서버 MVP 로그인 응답에 포함하는 단일 역할. 현재 서버 허용값은 `admin`, `manager`, `viewer`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member` |
| password_hash | 비밀번호 해시 |
| is_active | 로그인 허용 여부 |
| status | ACTIVE, LOCKED, DISABLED |
| created_at | 생성일 |
| updated_at | 수정일 |

### Role

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| role_id | 외부 참조용 역할 ID |
| role_name | 역할명 |
| description | 설명 |

기본 역할:

- `field-user`: 현장 사용자
- `document-admin`: 문서 관리자
- `system-admin`: 시스템 관리자

### UserRole

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| user_id | 사용자 ID |
| role_id | 역할 ID |
| created_at | 생성일 |

### OperatorProfile

현장 작업자, 작업반, 조장, 관리자 대리 등록자처럼 실제 현장 이력에 남겨야 하는 작업 주체를 관리한다. 모든 현장에서 작업자 개인을 1명씩 식별할 수 있는 것은 아니므로 개인, 그룹, 역할, 대리 등록자를 모두 표현할 수 있게 한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| operator_id | 외부 참조용 작업자/작업그룹 ID |
| operator_type | individual, group, lead, proxy_admin, external 등 |
| user_id | 로그인 계정과 연결되는 경우 사용자 ID |
| display_name | 표시명 |
| line_code | 라인 코드 |
| process_code | 공정 코드 |
| equipment_code | 설비 코드 |
| status | ACTIVE, INACTIVE |
| created_at | 생성일 |
| updated_at | 수정일 |

문서 수정, 문서 열람, 현장 코멘트, 작업내역은 가능한 경우 `UserAccount`와 `OperatorProfile`을 함께 남긴다. 사용자가 직접 입력하지 않고 관리자가 대리 등록한 경우에도 실제 전달자 또는 작업그룹을 추적할 수 있어야 한다.

### AuthSession

현재 FastAPI 서버는 HMAC 서명 access token만으로 인증 상태를 판단하지 않고 `auth_sessions` 테이블을 함께 검증한다. 이 테이블은 로그아웃, refresh token 회전, access token 폐기를 위한 서버 저장 세션 기준이다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| session_id | access token의 `sid`와 연결되는 외부 참조용 세션 ID |
| user_id | 사용자 ID |
| access_token_id | access token의 `jti`. refresh 시 새 값으로 교체되어 이전 access token을 폐기 |
| refresh_token_hash | 서버에 평문 refresh token을 저장하지 않기 위한 SHA-256 hash |
| status | ACTIVE, REVOKED, EXPIRED |
| access_expires_at | access token 만료일 |
| refresh_expires_at | refresh token 만료일 |
| revoked_at | 로그아웃 또는 관리자 폐기 시각 |
| revoked_reason | 폐기 사유 |
| last_used_at | 마지막 로그인/refresh 사용 시각 |
| created_at | 생성일 |

## 1. 문서 모델

### Document

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 외부 참조용 문서 ID |
| idempotency_key | 선택. WPF 로컬 등록 재시도 중복 방지를 위한 키 |
| title | 문서명 |
| description | 설명 |
| document_type | technical_document, drawing, manual, work_instruction 등 |
| owner_id | 소유자 |
| category_id | 분류 |
| status | WORKING, IN_REVIEW, PUBLISHED, ARCHIVED, DELETED |
| latest_version_id | 가장 최근 등록 버전 ID |
| published_version_id | 현장 공개 버전 ID |
| created_at | 생성일 |
| updated_at | 수정일 |
| deleted_at | 삭제 처리일 |

### FileObject

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| storage_type | local 우선. 후속 확장 시 nas, object 등 |
| storage_key | 저장소 경로 또는 object key |
| original_filename | 원본 파일명 |
| extension | 확장자 |
| mime_type | MIME 타입 |
| file_family | hwp, word, powerpoint, excel, pdf, dwg 등 |
| size_bytes | 파일 크기 |
| hash_sha256 | 무결성 검증용 해시 |
| created_at | 생성일 |

### DocumentVersion

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| idempotency_key | 선택. WPF 로컬 접근 로그 재시도 중복 방지를 위한 키 |
| document_id | 문서 ID |
| file_object_id | 파일 객체 ID |
| version_no | 버전 번호 |
| version_label | 표시용 버전명 |
| change_reason | 변경 사유 |
| version_status | WORKING, IN_REVIEW, APPROVED, PUBLISHED, SUPERSEDED, ARCHIVED |
| is_latest | 가장 최근 등록 버전 여부 |
| is_published | 현장 공개 버전 여부 |
| published_at | 현장 공개일 |
| created_by | 등록자 |
| created_at | 등록일 |

`change_reason`은 새 버전 등록 시 필수이다. 업로드된 문서가 항상 최신 확정본이라고 가정하지 않는다. 가장 최근 등록 버전은 `latest_version_id`, 현장 공개 대상 버전은 `published_version_id`로 구분한다.

서버 구현 기준으로 최초 업로드와 새 버전 업로드는 공개 버전을 자동 지정하지 않는다. 새 버전은 `version_status=WORKING`, `is_latest=true`, `is_published=false`로 시작한다. 공개 처리는 `POST /api/v1/documents/{documentId}/versions/{versionId}/publish`에서만 수행하며, 이때 기존 공개 버전의 `is_published`를 해제하고 대상 버전을 `PUBLISHED`로 전환한다. 현장 공개 조회는 `documents.published_version_id`와 함께 `document_versions.version_status=PUBLISHED`, `is_published=true`를 만족하는 버전만 반환한다.

## 2. 문서 보조 모델

### DocumentTag

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| tag_id | 태그 ID |
| created_at | 생성일 |

### TagDefinition

설비, 품목, 공정, 오류 유형 등 공통 태그 사전을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| tag_id | 외부 참조용 태그 ID |
| tag_type | equipment, item, process, error_type, line, location, custom 등 |
| code | 태그 코드 |
| name | 표시명 |
| parent_tag_id | 상위 태그 ID |
| external_system | 외부 시스템 코드 |
| external_ref_id | 외부 시스템 참조 ID |
| is_active | 사용 여부 |
| created_at | 생성일 |

### FieldCommentTag

현장 코멘트와 태그의 연결을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| comment_id | 현장 코멘트 ID |
| tag_id | 태그 ID |
| created_at | 생성일 |

문서 구조에 흡수되지 못한 관계는 태그로 보완한다. 같은 설비, 품목, 공정, 오류 유형 태그를 공유하는 문서와 현장 코멘트는 AI 검색과 보고서 생성에서 함께 참조할 수 있다.

### DocumentLink

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| system_code | 외부 시스템 코드 |
| entity_type | line, equipment, process, product 등 |
| entity_id | 연결 대상 ID |
| created_at | 생성일 |

`DocumentLink`는 외부 시스템의 단순 대상 연결에 사용한다. 고객이 정한 문서 정리 구조가 필요한 경우에는 `DocumentStructure` 모델을 사용한다.

## 2.1 외부 시스템 연동 모델

### ExternalSystem

MES, ERP, 기타 업무 시스템의 연결 정보를 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| system_id | 외부 참조용 시스템 ID |
| system_code | mes, erp, custom 등 |
| name | 시스템명 |
| integration_type | api, database, file |
| base_url | API 기준 주소 |
| is_active | 사용 여부 |
| created_at | 생성일 |
| updated_at | 수정일 |

### IntegrationMapping

외부 시스템의 원본 데이터와 FlowNote 내부 데이터를 연결한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| mapping_id | 외부 참조용 매핑 ID |
| system_id | 외부 시스템 ID |
| external_entity_type | work_order, item, process, equipment, production_result 등 |
| external_entity_id | 외부 시스템 원본 ID |
| flow_entity_type | document_structure, document_structure_item, work_record, field_comment, document 등 |
| flow_entity_id | FlowNote 내부 참조 ID |
| sync_status | PENDING, SYNCED, FAILED, DISABLED |
| last_synced_at | 마지막 동기화 일시 |
| created_at | 생성일 |

FlowNote는 외부 시스템의 원본 데이터를 임의로 대체하지 않는다. 매핑은 AI 검색과 조언에서 정형 생산 데이터와 현장지식 데이터를 함께 찾기 위한 연결 정보이다.

### DocumentStructure

고객이 정한 문서 정리 구조의 루트를 관리한다. 트리 구조는 가능한 표현 방식 중 하나일 뿐 기본 강제 구조가 아니다. 현장에서 말하는 BOM 문서 구조는 MES BOM이 아니라 문서를 계층적으로 정리해 부르는 현장 용어의 예시이다. 초기 작업지시서 구조는 MES 연동이 아니라 관리자가 직접 입력하는 `manual` 출처를 기본으로 한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| structure_id | 외부 참조용 구조 ID |
| structure_type | custom, work_order, project, folder, hierarchy 등 |
| title | 구조명 |
| source_type | manual, external |
| external_system | MES/ERP 등 외부 시스템 코드. 외부 연동 시 사용 |
| external_ref_id | 외부 프로젝트 또는 작업지시서 ID. 외부 연동 시 사용 |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### DocumentStructureItem

문서 구조의 항목을 관리한다. 트리 노드처럼 사용할 수도 있고, 고객이 쓰는 분류 항목처럼 사용할 수도 있다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| item_id | 외부 참조용 항목 ID |
| structure_id | 구조 ID |
| parent_item_id | 부모 항목 ID. 트리형 구조에서 사용 |
| item_type | folder, group, work_order, process, item, custom 등 |
| title | 항목명 |
| sort_order | 표시 순서 |
| external_ref_id | 외부 참조 ID. 외부 연동 시 사용 |
| created_at | 생성일 |
| updated_at | 수정일 |

### DocumentStructureItemDocument

문서 구조 항목과 문서의 연결을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| item_id | 구조 항목 ID |
| document_id | 문서 ID |
| document_version_id | 특정 버전을 고정 연결할 경우 사용 |
| link_type | required, reference, work_instruction, drawing 등 |
| created_at | 생성일 |

### DocumentPermission

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| subject_type | user, group, role, public |
| subject_id | 권한 주체 ID |
| permission | view, download, comment, write, delete, manage |
| created_at | 생성일 |

### DocumentHistory

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| document_version_id | 관련 버전 ID |
| event_type | 이벤트 유형 |
| before_value | 변경 전 값 |
| after_value | 변경 후 값 |
| change_reason | 변경 사유 |
| actor_id | 수행자 |
| created_at | 생성일 |

### DocumentAccessLog

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| document_version_id | 접근 버전 ID |
| action | 현재 서버 허용값은 `view_started`, `view_closed`, `download_blocked`, `auto_closed` |
| actor_id | 접근자 |
| device_id | 단말기 ID |
| client_ip | 클라이언트 IP |
| user_agent | User-Agent |
| created_at | 생성일 |

## 3. 단말기와 알림

### TerminalDevice

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| device_id | 외부 참조용 단말기 ID |
| device_name | 단말기명 |
| device_mode | viewer, admin_support |
| location_code | 위치 또는 현장 코드 |
| group_id | 단말기 그룹 ID |
| status | ACTIVE, INACTIVE |
| last_seen_at | 마지막 접속일 |
| created_at | 생성일 |

### Notification

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| notification_id | 외부 참조용 알림 ID |
| notification_type | WPF 로컬 기준 `document`, `work_sequence` |
| event_type | 서버 목표 모델 기준 DOCUMENT_VERSION_PUBLISHED 등 |
| title | 알림 제목 |
| message | 알림 내용 |
| document_id | 관련 문서 ID |
| document_version_id | 관련 버전 ID |
| target_type | WPF 로컬 기준 document, work_sequence_board, work_sequence_item 등 |
| target_id | WPF 로컬 대상 ID |
| target_title | WPF 로컬 대상 표시 제목 |
| source_candidate_id | 작업순서 알림이면 `work_sequence_notification_candidates.candidate_id` |
| recipient_target_type | 서버 목표 모델 기준 user, group, role, device, device_group |
| recipient_target_id | 서버 목표 모델 기준 대상 ID |
| status | PENDING, SENT, READ, FAILED |
| created_at | 생성일 |
| sent_at | 발송일 |
| read_at | 읽은 일시 |

알림 이벤트는 문서 공개, 새 버전 등록, 현장 코멘트 등록, 사진 기록 등록, 작업순서 변경, 작업순서 상태 변경을 포함한다.

WPF 로컬 알림함은 기존 문서 알림과 작업순서 알림을 같은 `notifications` 테이블에 저장하고 `notification_type`으로 구분한다. 작업순서 알림을 읽으면 `activity_history`에 `work_sequence.notification_read`가 남는다.

### ViewerSession

문서 뷰어 열람 세션과 자동 닫힘 시간을 관리한다. 이 모델은 Windows WPF 클라이언트 앱과 Python FastAPI 서버의 감사 로그 연동에서 사용한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| viewer_session_id | 외부 참조용 뷰어 세션 ID |
| document_id | 문서 ID |
| document_version_id | 문서 버전 ID |
| user_id | 사용자 ID |
| device_id | 단말기 ID |
| opened_at | 열람 시작일 |
| expires_at | 자동 닫힘 예정일 |
| closed_at | 실제 닫힘 일시 |
| close_reason | user_closed, timeout, permission_revoked |

## 4. 관리자 파일 감시

### WatchedFile

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| watched_file_id | 외부 참조용 감시 항목 ID |
| device_id | 관리자 단말기 ID |
| document_id | 연결 문서 ID |
| local_path | 감시 대상 경로 |
| watch_type | file, folder |
| last_modified_at | 마지막 수정일 |
| last_size_bytes | 마지막 파일 크기 |
| last_hash_sha256 | 마지막 해시 |
| status | ACTIVE, PAUSED, REMOVED |
| created_by | 등록자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### FileChangeCandidate

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| candidate_id | 외부 참조용 후보 ID |
| watched_file_id | 감시 항목 ID |
| document_id | 연결 문서 ID |
| detected_modified_at | 감지 수정일 |
| detected_size_bytes | 감지 파일 크기 |
| detected_hash_sha256 | 감지 해시 |
| status | 서버 목표 모델 기준 DETECTED, IGNORED, UPLOADED. 현재 WPF 로컬 `file_watch_candidates`는 `PENDING`, `CONFIRMED`, `IGNORED`를 사용 |
| uploaded_version_id | 업로드된 버전 ID |
| detected_at | 감지일 |
| resolved_at | 처리일 |

## 5. 현장 코멘트와 보고서

### FieldComment

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| comment_id | 외부 참조용 문구 ID |
| idempotency_key | 선택. WPF 로컬 FieldComment 재시도 중복 방지를 위한 키 |
| document_id | 연결 문서 ID |
| document_version_id | 연결 버전 ID |
| structure_item_id | 연결 문서 구조 항목 ID |
| work_record_id | 연결 작업내역 ID |
| comment_type | experience, work_evaluation, issue |
| input_mode | signal, free_text, template, template_with_text, admin_proxy, mes_integration |
| signal_level | green, yellow, red 등 단순 상태 값 |
| template_id | 선택한 정형 문구 ID |
| raw_content | 현장 사용자 입력 원문 |
| normalized_content | 관리자 정리 문구 |
| analysis_content | 관리자 분석 내용 |
| author_id | 입력자 |
| reported_by | 실제 현장 전달자 또는 작업자 |
| operator_id | 작업자 또는 작업그룹 ID |
| entry_source | field_user, admin_proxy, mes, system |
| device_id | 단말기 ID |
| location_code | 위치 또는 현장 코드 |
| category | 분류 |
| priority | 중요도 |
| status | NEW, NEEDS_REVIEW, ANALYZED, REVIEWED, SELECTED, EXCLUDED, ARCHIVED |
| reviewed_by | 검토자 |
| analyzed_by | 분석자 |
| created_at | 등록일 |
| updated_at | 수정일 |
| reviewed_at | 검토일 |
| analyzed_at | 분석일 |

`FieldComment`는 최소 하나의 연결 대상이 있어야 한다. 현재 서버 API는 `document_id`, `structure_item_id`, `work_record_id` 중 하나 이상을 요구한다. `document_version_id`가 있으면 서버 `document_versions.version_id`와 일치해야 하며, `document_id`와 함께 들어온 경우 같은 문서의 버전이어야 한다. 1차 MVP에서는 문서 또는 문서 버전 연결을 우선 사용하고, 문서 구조 항목과 작업내역 연결은 후속 단계에서 확장한다.

초기 현장 입력은 많은 텍스트를 요구하지 않는다. `signal`은 정상, 주의, 문제 같은 신호등식 기록이고, `admin_proxy`는 현장 사용자가 말로 전달한 내용을 관리자가 대신 등록하는 방식이다. `mes_integration`은 MES나 자동화 시스템 연동 이후 사용한다.

`raw_content`는 원천 이력, `normalized_content`는 관리자 정리 문구, `analysis_content`는 관리자급 사용자의 판단과 분석이다. 코멘트만 쌓아서는 실제 활용이 어려우므로, 보고서 작성 시 어떤 원천 코멘트가 어떤 분석과 결론으로 이어졌는지 추적해야 한다.

### FieldCommentAttachment

현장 코멘트 또는 일일 작업일지성 기록에 첨부된 사진과 파일을 관리한다. 사진은 보고서 자동화의 원천 데이터가 될 수 있지만, 1차 MVP에서는 첨부, 열람, 이력 추적을 우선한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| attachment_id | 외부 참조용 첨부 ID |
| comment_id | 현장 코멘트 ID |
| file_object_id | 첨부 파일 객체 ID |
| attachment_type | photo, document, other |
| caption | 현장 메모 또는 사진 설명 |
| captured_at | 촬영 시각. 알 수 있는 경우 |
| created_by | 등록자 |
| created_at | 등록일 |

### CommentTemplate

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| template_id | 외부 참조용 템플릿 ID |
| title | 표시 문구 |
| content | 기본 등록 문구 |
| comment_type | 문구 유형 |
| document_type | 적용 문서 유형 |
| category | 분류 |
| location_code | 적용 위치 |
| is_active | 사용 여부 |
| sort_order | 표시 순서 |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### Report

현장 코멘트, 작업내역, 관련 문서를 기반으로 관리자가 정리한 보고서를 관리한다. AI는 보고서 초안을 도울 수 있지만, 최종 보고서는 관리자급 사용자의 검토를 거친 문서로 남긴다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| report_id | 외부 참조용 보고서 ID |
| report_type | production, issue, improvement, inspection, custom 등 |
| title | 보고서 제목 |
| summary | 요약 |
| analysis_content | 관리자 분석 내용 |
| conclusion | 결론 |
| action_plan | 조치 계획 |
| work_record_id | 관련 작업내역 ID |
| structure_item_id | 관련 문서 구조 항목 ID |
| period_start | 보고 대상 시작일 |
| period_end | 보고 대상 종료일 |
| status | DRAFT, AI_DRAFTED, REVIEWED, APPROVED, ARCHIVED |
| ai_draft_used | AI 초안 사용 여부 |
| generated_document_id | 최종 문서로 저장된 Document ID |
| created_by | 작성자 |
| reviewed_by | 검토자 |
| approved_by | 승인자 |
| created_at | 생성일 |
| reviewed_at | 검토일 |
| approved_at | 승인일 |

### ReportSource

보고서가 어떤 원천 데이터에서 만들어졌는지 추적한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| report_id | 보고서 ID |
| source_type | FIELD_COMMENT, DOCUMENT, WORK_SEQUENCE_ITEM, WORK_SEQUENCE_HISTORY, WORK_RECORD, WORK_RECORD_VERSION |
| source_id | 원천 데이터 ID |
| source_version_id | 원천 버전 ID |
| relation_type | evidence, issue, action, reference 등 |
| created_at | 생성일 |

최종 보고서는 `Document`로 저장하고 원천 코멘트, 작업내역, 관련 문서는 `ReportSource`로 추적한다. 보고서만 있으면 상세 이력을 알기 어렵고, 원천 이력만 있으면 의사결정에 쓰기 어렵기 때문에 두 계층을 모두 유지한다.

## 6. 작업내역과 AI

### WorkRecord

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 외부 참조용 작업내역 ID |
| work_order_no | 작업지시 번호 |
| title | 작업 제목 |
| work_instruction_document_id | 작업지시 문서 ID |
| source_type | manual, external |
| external_system | MES/ERP 등 외부 시스템 코드. 외부 연동 시 사용 |
| external_ref_id | 외부 작업지시 ID. 외부 연동 시 사용 |
| status | DRAFT, ACTIVE, COMPLETED, ARCHIVED |
| latest_version_id | 가장 최근 등록 작업내역 버전 ID |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### WorkRecordVersion

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| version_no | 버전 번호 |
| summary | 작업 요약 |
| result_note | 작업 결과 |
| issue_note | 발생 문제 |
| action_note | 조치 내용 |
| change_reason | 변경 사유 |
| created_by | 등록자 |
| created_at | 등록일 |

### WorkRecordDocument

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| document_id | 관련 문서 ID |
| document_version_id | 관련 문서 버전 ID |
| relation_type | instruction, reference, evidence |
| created_at | 생성일 |

### WorkRecordParticipant

작업내역에 참여하거나 보고된 작업 주체를 연결한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| operator_id | 작업자 또는 작업그룹 ID |
| user_id | 로그인 사용자 ID. 있는 경우 |
| role_type | worker, lead, supervisor, reporter, reviewer 등 |
| created_at | 생성일 |

### WorkSequenceBoard

사무실, 관리자, 반장, 조장이 현장 처리 순서를 공유하기 위한 작업순서판을 관리한다. 작업순서판은 MES 작업지시를 대체하지 않고, 현재 현장에서 어떤 순서로 처리할지 보여주는 운영 화면이다. 2026-06-29 현재 서버와 WPF 로컬 구현은 관리자 입력 기준의 최소 모델이며, 기존 `작업순서` 폴더 파일 등록과 분리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| board_id | 외부 참조용 작업순서판 ID |
| title | 작업순서판명 |
| description | 설명 |
| line_code | 라인 또는 현장 코드 |
| board_date | 기준 날짜 |
| status | ACTIVE, ARCHIVED |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### WorkSequenceItem

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| item_id | 외부 참조용 작업순서 항목 ID |
| board_id | 작업순서판 ID |
| title | 표시 제목 |
| description | 설명 |
| work_order_no | 관리자 입력 작업번호 또는 외부 작업지시 참조 문자열 |
| document_id | 필요 시 관련 문서 ID |
| status | WAITING, IN_PROGRESS, HOLD, COMPLETED |
| hold_reason | `HOLD` 상태의 보류 사유. 상태가 HOLD가 아니면 비울 수 있음 |
| sort_order | 표시 순서 |
| assigned_to | 작업반, 조장, 담당자 표시 문자열 |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### WorkSequenceHistory

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| change_id | 외부 참조용 변경 ID |
| board_id | 작업순서판 ID |
| item_id | 작업순서 항목 ID. 보드 전체 순서 변경이면 비울 수 있음 |
| change_type | BOARD_CREATED, ITEM_ADDED, ITEM_REORDERED, STATUS_CHANGED, HOLD_REASON_CHANGED |
| before_value | 변경 전 값 |
| after_value | 변경 후 값 |
| change_reason | 변경 사유 또는 메모 |
| actor_id | 수행자 |
| created_at | 생성일 |

### WorkSequenceNotificationCandidate

작업순서 변경 알림 이벤트 후보를 저장한다. 현재 최소 구현은 순서 변경, 상태 변경, 보류 사유 변경 시 후보를 남긴다. WPF 로컬 앱은 후보 생성 직후 기존 `notifications` 알림함에 `work_sequence` 타입 알림을 만들고 후보를 `SENT` 또는 `DISMISSED`로 바꾼다. 서버 API는 후보 상태 전환 흐름을 제공하되, 실제 외부 발송 채널은 후속 알림 정책에서 확장한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| candidate_id | 외부 참조용 후보 ID |
| board_id | 작업순서판 ID |
| item_id | 관련 작업순서 항목 ID |
| event_type | work_sequence.reordered, work_sequence.status_changed, work_sequence.hold_reason_changed 등 |
| actor_id | 수행자 |
| recipient_hint | 담당자 또는 라인 힌트 |
| message | 알림 후보 메시지 |
| status | CANDIDATE, SENT, DISMISSED. WPF 로컬은 알림 생성 성공 시 SENT, 수신자 없음 또는 자기 알림이면 DISMISSED |
| created_at | 생성일 |

### SearchIndexItem

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| source_type | document_version, field_comment, report, work_record_version |
| source_id | 원천 데이터 ID |
| source_version_id | 원천 버전 ID |
| title | 검색 표시 제목 |
| content_text | 검색 대상 텍스트 |
| permission_scope | 검색 권한 범위 |
| indexed_at | 인덱싱 일시 |

### AiAdviceLog

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| advice_id | 외부 참조용 조언 ID |
| request_type | search, work_advice, risk_preview |
| query | 사용자 질의 또는 분석 요청 |
| work_record_id | 관련 작업내역 ID |
| document_id | 관련 문서 ID |
| response_summary | AI 응답 요약 |
| source_refs | 근거 참조 목록 |
| created_by | 요청자 |
| created_at | 생성일 |

### ClientLocalActionLog

Windows WPF 클라이언트 앱의 로컬 기능 호출 중 감사가 필요한 요청을 기록한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| local_action_id | 외부 참조용 로컬 기능 감사 ID |
| device_id | 단말기 ID |
| user_id | 사용자 ID |
| action | 로컬 기능 액션명 |
| request_summary | 요청 요약 |
| result | success, denied, failed |
| created_at | 생성일 |

## 7. 식별자 원칙

- 내부 DB 식별자와 외부 참조용 ID를 분리한다.
- 외부에는 `user_id`, `operator_id`, `session_id`, `document_id`, `structure_id`, `item_id`, `viewer_session_id`, `comment_id`, `report_id`, `notification_id`, `work_record_id`, `advice_id`, `watched_file_id`, `candidate_id`, `local_action_id`를 노출한다.
- 외부 참조용 ID는 변경하지 않는다.
- 물리 삭제보다 상태 변경을 우선한다.
