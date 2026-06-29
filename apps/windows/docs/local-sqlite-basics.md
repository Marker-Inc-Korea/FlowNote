# 로컬 SQLite 기본 구조

## 목적

Windows WPF 앱은 서버 연결 여부와 관계없이 현장 문서 등록, 열람, FieldNote, 첨부, 작업순서, 이력 저장을 로컬 SQLite에 먼저 기록한다. 서버가 설정되어 있으면 로컬 저장 이후 동기화를 시도한다.

## 기본 설정

- DB 파일명: `flownote.local.sqlite`
- 개발 실행 기본 경로: 저장소 루트의 `data/local/flownote.local.sqlite`
- 배포 실행 기본 경로: 앱 실행 폴더의 `Data\flownote.local.sqlite`
- 데이터 폴더 override: `FLOWNOTE_LOCAL_DATA_DIR`
- DB 파일 override: `FLOWNOTE_LOCAL_DATABASE_PATH`
- 기본 로그인: `admin / 1234`
- 개발/스모크 테스트 계정: 관리자 그룹, 반장, 조장, 조원 계정. 모든 비밀번호는 `1234`

테스트와 스모크 테스트는 같은 공통 SQLite DB에 기록을 누적한다. 사용자가 명시적으로 삭제를 지시하지 않는 한 DB와 테스트 산출물을 삭제하지 않는다.

## 현재 테이블

- `user_accounts`: 로컬 로그인 계정, role, 그룹/상위자 정보
- `user_groups`: 관리자 그룹과 작업조
- `document_folders`: 루트, 기본 폴더, 분류 폴더, 날짜 폴더
- `documents`: 문서 메타데이터, 상태, 로컬 경로, 최신/공개 버전, 서버 ID 후보
- `document_versions`: 문서 파일 버전, 공개 여부, 서버 버전 ID 후보
- `field_notes`: 현장 코멘트 원천 이력
- `field_note_attachments`: FieldNote 사진/파일 첨부와 로컬 보존 경로
- `document_view_logs`: 문서 열람 시작/닫힘 감사 로그와 서버 로그 ID 후보
- `activity_history`: 폴더, 문서, FieldNote, 첨부, 동기화, 작업순서 변경 이력
- `tag_definitions`, `document_tags`: 문서 태그 사전과 문서-태그 연결
- `notifications`: 문서/FieldNote 관련 로컬 알림
- `work_sequence_boards`, `work_sequence_items`: 운영용 작업순서판과 항목
- `work_sequence_change_history`: 작업순서 항목 추가, 순서 변경, 상태 변경 이력
- `work_sequence_notification_candidates`: 작업순서 변경 알림 이벤트 후보
- `server_sync_queue`: 문서, FieldNote, 첨부, 접근 로그 전송 후보와 실패/성공 상태
- `server_id_mappings`: 로컬 ID와 서버 ID 매핑

## 서비스 위치

- `FlowNoteLocalDatabase`: SQLite 파일 생성, 스키마 생성, 기본 데이터 시드
- `FlowNoteLocalServices`: 로컬 서비스 묶음
- `AuthService`: 로컬 로그인 검증
- `FolderService`: 폴더 생성, 목록, 삭제
- `DocumentService`: 문서 등록, 버전, 공개 처리, 목록 조회
- `FieldNoteService`: FieldNote와 첨부 저장/조회
- `DocumentViewLogService`: 문서 열람 로그 기록
- `HistoryService`: 전체 이력 기록/조회
- `NotificationService`: 알림 생성/조회/읽음 처리
- `TagService`: 태그 저장/조회
- `WorkSequenceService`: 작업순서판, 항목, 순서, 상태, 이력 관리
- `ServerSyncService`: 서버 전송 큐, 재시도, 서버 ID 매핑 관리
- `DocumentPlacementService`: 기본 폴더별 문서 배치 규칙

## 동기화 원칙

로컬 저장은 서버 전송보다 우선한다. 서버 URL이 없거나 전송에 실패해도 로컬 문서, FieldNote, 첨부, 접근 로그는 보존한다. 실패 사유는 `server_sync_queue.last_error`와 `activity_history`에 기록한다.

동기화 성공 시 다음 값을 갱신한다.

- `documents.server_document_id`
- `documents.server_version_id`
- `documents.synced_at`
- `document_versions.server_version_id`
- `field_notes.server_note_id`
- `field_notes.synced_at`
- `field_note_attachments.server_attachment_id`
- `field_note_attachments.synced_at`
- `document_view_logs.server_start_log_id`
- `document_view_logs.server_close_log_id`
- `document_view_logs.synced_at`
- `server_id_mappings`

현재 FastAPI 서버는 별도 idempotency key 요청 필드를 받지 않는다. 중복 방지는 로컬 큐의 idempotency key, 서버 ID, `synced_at` 확인으로 수행한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```
