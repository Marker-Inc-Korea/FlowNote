# 로컬 SQLite 기본 구조

## 목적

Windows WPF 앱은 서버 연결 여부와 관계없이 현장 문서와 기록을 로컬 SQLite에 먼저 남긴다. 서버가 설정되어 있으면 이후 동기화를 시도한다.

## 경로

- DB 파일명: `flownote.local.sqlite`
- 기본 개발 경로: `data/local/flownote.local.sqlite`
- 배포 실행 기본 경로: 저장소 루트를 찾을 수 없을 때 실행 폴더의 `Data/flownote.local.sqlite`
- 데이터 폴더 override: `FLOWNOTE_LOCAL_DATA_DIR`
- DB 파일 override: `FLOWNOTE_LOCAL_DATABASE_PATH`

## 주요 테이블

- `user_accounts`: 로컬 로그인 계정과 role
- `user_groups`: 관리자 그룹과 작업조
- `document_folders`: 폴더 트리
- `documents`: 문서 메타데이터, 최신/공개 버전, 서버 ID
- `document_versions`: 파일 버전, 변경 사유, 공개 여부, 서버 버전 ID
- `field_comments`: FieldComment 원천 기록, 서버 코멘트 ID
- `field_comment_attachments`: FieldComment 첨부와 서버 첨부 ID
- `document_view_logs`: 열람/닫힘/차단 로그와 서버 로그 ID
- `activity_history`: 전체 활동 이력
- `file_watch_candidates`: 파일 감시 후보
- `tag_definitions`, `document_tags`: 태그
- `notifications`: 알림
- `work_sequence_boards`, `work_sequence_items`: 작업순서
- `work_sequence_change_history`: 작업순서 이력
- `work_sequence_notification_candidates`: 작업순서 알림 후보
- `report_sources`: 로컬 보고서 문서와 근거 source 연결
- `server_sync_queue`: 서버 전송 큐
- `server_id_mappings`: 로컬 ID와 서버 ID 연결

기존 공통 SQLite에는 FieldComment 명칭 전환 전 테스트 이력인 `field_notes`, `field_note_attachments`가 남아 있을 수 있다. 이 테이블과 관련 `server_sync_queue`의 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 항목은 새 기능의 작성 대상이 아니다. 현재 WPF는 이를 구 FieldNote 큐로 분류하고 자동 서버 전송하지 않으며, 운영자가 FieldComment 전환 또는 별도 마이그레이션 대상으로 검토한다.

## 기본 시드

로컬 DB 초기화 시 관리자 그룹과 A/B/C 라인 작업조, 관리자/반장/조장/조원 계정을 만든다. 모든 개발/스모크 테스트 계정의 기본 비밀번호는 `1234`이다.

WPF 사용자 관리 화면은 이 로컬 SQLite 계정 전용이다. 창 제목, 사용자 목록, 사용자 상세 안내는 “로컬” 계정임을 표시해야 하며 서버 계정 발급, 잠금, 비밀번호 재설정, role 변경은 서버 PC의 `app.ops.server_accounts` 운영 스크립트에서 수행한다.

## 동기화 원칙

로컬 저장이 우선이다. 서버 URL이 없거나 서버 호출이 실패해도 로컬 문서, 문서 버전/공개/상태, FieldComment, 첨부, 접근 로그는 유지된다. 동기화 성공 시 원천 테이블의 서버 ID와 `synced_at`, `server_id_mappings`를 갱신한다.

구 FieldNote 큐는 동기화 실패 기록이 남아 있어도 FieldComment API로 자동 변환하지 않는다. 테스트/스모크 이력 보존 규칙에 따라 기존 SQLite row와 큐 기록은 삭제하지 않고, 이력 창의 분류와 조치 문구로 별도 정리 대상으로 표시한다.

문서 최신 버전은 `documents.version_no`와 `document_versions.is_latest`를 기준으로 서버 최신 버전에 연결한다. 공개 버전은 `documents.published_version_no`와 `document_versions.is_published`를 기준으로 서버 publish API에 반영한다. 상태 변경은 현재 로컬 `documents.status`를 서버에 반영하며, `PUBLISHED` 상태는 공개 버전 동기화가 선행되어야 한다.

보고서는 로컬 보고서 문서와 `report_sources`를 먼저 만든 뒤 서버 저장을 시도한다. 서버 저장이 성공하면 `server_report_id`, `server_document_id`, `server_version_id`, `server_id_mappings`를 함께 남기고, 실패하면 `server_sync_queue`에 `report/register_report` 재시도 항목을 보존한다. 작업순서 보드/항목/이력은 현재 단계에서 로컬 큐 대상이 아니라 로컬 기록과 서버 직접 API 검증, 보고서 근거 source 연결 범위로 둔다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```
