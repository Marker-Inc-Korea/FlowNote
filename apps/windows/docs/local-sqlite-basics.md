# 로컬 SQLite 기본 구조

## 목적

Windows WPF 앱은 서버 연결 여부와 관계없이 현장 문서와 기록을 로컬 SQLite에 먼저 남긴다. 서버가 설정되어 있으면 이후 동기화를 시도한다.

## 경로

- DB 파일명: `flownote.local.sqlite`
- 기본 개발 경로: `data/local/flownote.local.sqlite`
- 배포 실행 기본 경로: 실행 폴더의 `Data/flownote.local.sqlite`
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
- `server_sync_queue`: 서버 전송 큐
- `server_id_mappings`: 로컬 ID와 서버 ID 연결

## 기본 시드

로컬 DB 초기화 시 관리자 그룹과 A/B/C 라인 작업조, 관리자/반장/조장/조원 계정을 만든다. 모든 개발/스모크 테스트 계정의 기본 비밀번호는 `1234`이다.

## 동기화 원칙

로컬 저장이 우선이다. 서버 URL이 없거나 서버 호출이 실패해도 로컬 문서, FieldComment, 첨부, 접근 로그는 유지된다. 동기화 성공 시 원천 테이블의 서버 ID와 `synced_at`, `server_id_mappings`를 갱신한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```
