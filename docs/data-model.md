# FlowNote 데이터 모델

## WPF 로컬 SQLite

기본 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 설정되면 해당 위치를 우선한다.

현재 WPF 로컬 DB 테이블은 다음과 같다.

| 테이블 | 역할 |
| --- | --- |
| `user_accounts` | 로그인 계정, 표시 이름, role, 그룹/상위자, 상태 |
| `user_groups` | 관리자 그룹과 라인별 작업조 |
| `document_folders` | 루트, 기본 폴더, 분류/날짜 폴더 |
| `documents` | 로컬 문서 메타데이터, 최신 버전, 공개 버전, 서버 ID |
| `document_versions` | 문서 버전, 파일 경로, 변경 사유, 공개 여부, 서버 버전 ID |
| `field_comments` | 현장 코멘트 원천 기록과 서버 코멘트 ID |
| `field_comment_attachments` | FieldComment 첨부 파일 로컬 경로와 서버 첨부 ID |
| `document_view_logs` | 문서 열람 시작/종료, 자동 닫힘, 다운로드 차단 로그 |
| `activity_history` | 폴더, 문서, 사용자, 파일 감시, 동기화, 작업순서 이력 |
| `file_watch_candidates` | 관리자 파일 감시 후보 |
| `tag_definitions` | 태그 사전 |
| `document_tags` | 문서-태그 연결 |
| `notifications` | 문서/FieldComment/작업순서 알림 |
| `work_sequence_boards` | 작업순서 보드 |
| `work_sequence_items` | 작업순서 항목과 상태 |
| `work_sequence_change_history` | 작업순서 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `server_sync_queue` | 서버 전송 대기/실패/성공 상태 |
| `server_id_mappings` | 로컬 ID와 서버 ID 매핑 |

## FastAPI 서버 SQLite

서버 기본 DB 경로는 `services/api/data/flownote.sqlite3`이고 테스트 DB 기본 경로는 `services/api/data/flownote.test.sqlite3`이다. 서버 파일은 기본적으로 `services/api/storage/` 아래 저장된다.

서버 ORM 테이블은 다음과 같다.

| 테이블 | 역할 |
| --- | --- |
| `schema_migrations` | 스키마 적용 버전 기록 |
| `user_accounts`, `roles`, `user_roles` | 계정과 역할 기반 권한 |
| `auth_sessions` | access token ID, refresh token hash, 세션 만료/폐기 상태 |
| `operator_profiles` | 작업자/작업그룹/대리 입력 주체 |
| `file_objects` | 서버 로컬 파일 참조, MIME, 크기, SHA-256 |
| `documents`, `document_versions` | 문서, 버전, 최신/공개 버전 |
| `tag_definitions`, `document_tags` | 태그 사전과 문서 연결 |
| `terminal_devices` | 현장 단말기 기준 정보 |
| `field_comments`, `field_comment_attachments` | 현장 코멘트와 첨부 |
| `comment_templates` | 정형 코멘트 문구 |
| `work_records`, `work_record_versions` | 작업내역 모델 기반 |
| `work_sequence_boards`, `work_sequence_items` | 작업순서 보드와 항목 |
| `work_sequence_change_history` | 작업순서 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `reports`, `report_sources` | 보고서와 근거 연결 |
| `document_access_logs` | 서버 문서 접근 로그 |
| `activity_history` | 서버 활동 이력 |

## 상태 값

문서 상태:

- `WORKING`
- `IN_REVIEW`
- `PUBLISHED`
- `ARCHIVED`

서버 문서 버전 상태:

- `WORKING`
- `IN_REVIEW`
- `APPROVED`
- `PUBLISHED`
- `SUPERSEDED`
- `ARCHIVED`

FieldComment 상태:

- `NEW`
- `NEEDS_REVIEW`
- `ANALYZED`
- `REVIEWED`
- `SELECTED`
- `EXCLUDED`
- `ARCHIVED`

작업순서 항목 상태:

- `WAITING`
- `IN_PROGRESS`
- `HOLD`
- `COMPLETED`

작업순서 알림 후보 상태:

- `CANDIDATE`
- `SENT`
- `DISMISSED`

서버 동기화 큐 상태:

- `PENDING`
- `FAILED`
- `SYNCED`

## 역할 값

현재 코드의 role 값은 다음과 같다.

- `admin`
- `system-admin`
- `document-admin`
- `manager`
- `assistant-manager`
- `department-manager`
- `line-foreman`
- `team-lead`
- `team-member`
- `viewer`

WPF 사용자 관리는 위 role 중 하나만 선택할 수 있다. 새 사용자 ID는 `user-{loginId}` 형식으로 자동 생성된다.
