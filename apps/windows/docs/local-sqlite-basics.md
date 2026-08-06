# 로컬 SQLite 기본 구조

## 목적

Windows WPF 앱은 문서, FieldComment, 첨부, 접근 로그, 보고서 같은 로컬 원천을 SQLite에 먼저 남기고 서버가 설정되어 있으면 동기화를 시도한다. 작업순서는 예외로 FastAPI snapshot을 권위 원천으로 직접 사용하며, 이 문서의 로컬 작업순서 테이블은 기존 기록·오프라인 읽기 캐시·초안으로만 보존한다.

테이블과 동기화 설명은 2026-08-06 현재 `FlowNoteLocalDatabase`와 연결 서비스 코드 기준이다.

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
- `documents`: 문서 메타데이터, 최신/공개 버전, 서버 ID·revision·태그 집합, 보고서 서버 revision·내용 hash·source 집합 hash read-back
- `document_versions`: 파일 버전, 변경 사유, 공개 여부, 서버 버전 ID
- `field_comments`: FieldComment 원천 기록, 서버 코멘트 ID, 마지막 검토 revision
- `field_comment_attachments`: FieldComment 첨부와 서버 첨부 ID
- `field_comment_saved_views`: FieldComment 목록의 저장된 필터 이름·JSON·갱신 시각
- `document_view_logs`: 열람/닫힘/차단 로그와 서버 로그 ID
- `activity_history`: 전체 활동 이력
- `file_watch_candidates`: 파일 감시 후보
- `tag_definitions`, `document_tags`: 태그
- `notifications`: 알림
- `server_notification_cursors`: 정규화한 서버 scope와 서버 사용자 ID별 마지막 성공 알림 cursor, 서버 관측 cursor, 상태와 갱신/관리자 초기화 시각
- `server_notification_messages`: 서버 scope와 사용자별 처리 완료 `message_id`, cursor와 처리 시각. 재조회 멱등 처리 근거
- `server_bindings`: 서버 scope별 승인 instance/epoch와 관측값, schema/API contract, 복구 경계 차단 상태, 승인 후 재시작·재검증 상태와 관리자 승인 감사
- `reconciliation_runs`, `reconciliation_items`: 전체 동기화 큐 inventory의 서버 대조 run, 항목별 판정·제안/적용 조치, 서버 ID/revision/hash와 해결 감사
- `work_sequence_boards`, `work_sequence_items`: 작업순서
- `work_sequence_change_history`: 작업순서 이력
- `work_sequence_notification_candidates`: 작업순서 알림 후보
- `report_sources`: 로컬 보고서 문서와 근거 source 연결
- `server_sync_queue`: 서버 전송 큐. 문서 aggregate 기준값과 태그 delta payload 외에 FieldComment 검토 `base_domain_revision`·의도 hash와 보고서 source 집합 hash를 additive 열로 보존
- `server_id_mappings`: 로컬 ID와 서버 ID 연결
- `server_sync_migration_audit`: 승인 전환한 보존 FAILED 큐와 신규 큐의 무손실 연결. 일반 DB 초기화가 아니라 전환 CLI 승인 실행 시 필요한 경우 생성

2026-07-20 controlled copy schema 보존 복구를 적용한 DB에는 `preserved_server_controlled_copy_grants`와 `local_schema_migration_audit`도 남는다. 두 테이블은 앱 기능이나 정상 초기화 대상이 아니라 잘못 유입된 서버 grant 값, 원래 DDL, 복구 run ID와 보호 대상 row hash를 보존하는 감사 증거다.

기존 공통 SQLite에는 FieldComment 명칭 전환 전 테스트 이력인 `field_notes`, `field_note_attachments`가 남아 있을 수 있다. 이 테이블과 관련 `server_sync_queue`의 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 항목은 새 기능의 작성 대상이 아니다. 현재 WPF는 이를 구 FieldNote 큐로 분류하고 자동 서버 전송하지 않으며, 운영자가 FieldComment 전환 또는 별도 마이그레이션 대상으로 검토한다.

## 기본 시드

로컬 DB 초기화 시 관리자 그룹과 A/B/C 라인 작업조, 관리자/반장/조장/조원 계정을 만든다. 모든 개발/스모크 테스트 계정의 기본 비밀번호는 `1234`이다.

로컬 로그인에서 여는 WPF 사용자 관리 화면은 이 로컬 SQLite 계정 전용이다. 창 제목, 사용자 목록, 사용자 상세 안내는 “로컬” 계정임을 표시한다. 서버 로그인한 `admin`, `system-admin`은 별도 서버 계정 화면과 FastAPI API로 계정 발급, 잠금·비활성화, 비밀번호 재설정, role 변경과 세션 폐기를 수행하며 로컬 계정 row를 덮어쓰지 않는다. 서버 PC의 `app.ops.server_accounts`는 초기·비상 운영 경로로만 유지한다.

## 동기화 원칙

로컬 저장이 우선이다. 서버 URL이 없거나 서버 호출이 실패해도 로컬 문서, 문서 버전/공개/상태/태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서는 유지된다. 동기화 성공 시 원천 테이블의 서버 ID와 `synced_at`, `server_id_mappings`를 갱신한다.

재시도 큐는 같은 문서 또는 보고서 근거 단위로 묶은 뒤 문서 등록, 문서 버전, 누적 구 공개 큐, 상태, 태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 순서로 처리한다. 현재 UI의 문서 공개는 서버 승인 작업함에서 직접 처리하므로 새 공개 큐를 만들지 않는다. 선행 문서, 문서 버전, FieldComment, 보고서 근거 서버 ID가 없으면 해당 항목은 `FAILED` 상태와 한글 보류 사유를 유지하되 실제 서버 호출과 `attempt_count` 증가는 하지 않는다.

구 FieldNote 큐는 동기화 실패 기록이 남아 있어도 일반 재시도에서 FieldComment API로 자동 변환하지 않는다. 테스트/스모크 이력 보존 규칙에 따라 기존 SQLite row와 큐 기록은 삭제하지 않고, 이력 창의 분류와 조치 문구로 별도 정리 대상으로 표시한다. 별도 전환 CLI는 dry-run 결과와 plan hash를 확인한 뒤 운영자가 승인한 row만 결정적인 새 FieldComment/첨부 ID와 현재 action의 신규 큐로 복제하며, 구 원천과 기존 FAILED 큐는 그대로 보존한다.

기존 공통 SQLite에는 초기 로컬 큐 형식의 `create` action이 남아 있을 수 있다. 현재 서버 동기화 코드는 `register_document`, `register_document_version`, `publish_document_version`, `update_document_status`, `replace_document_tags`, `register_field_comment`, `update_field_comment_review`, `register_field_comment_attachment`, `register_access_log_*`, `register_report`만 서버 전송 action으로 처리한다. 따라서 `document/create`, `document_version/create`, `document_view_log/create`, `field_comment/create`, `field_comment_attachment/create`는 일반 재시도에서 새 동기화 계약으로 재해석하지 않는다. 재시도 시 행과 원본 데이터를 삭제하지 않고 `FAILED`와 구 형식 보류 사유를 기록하며, 실제 서버 호출과 `attempt_count` 증가는 하지 않는다. 별도 전환 CLI는 `document`, `document_version`, `field_comment`, `field_comment_attachment`의 구 `create`를 현재 등록 action으로 분류하고, `document_view_log/create`는 종료 시각과 종료 사유에 따라 열람 시작·종료·자동 종료·다운로드 차단 action으로 해석해 관리자 확인 대상으로 둔다.

전환 CLI의 dry-run은 DB를 read-only로 열어 감사 테이블이나 큐를 만들지 않는다. 승인 실행만 `server_sync_migration_audit`를 만들고 원천 큐 ID, 대상 idempotency key, 승인자, plan hash, 원천 JSON snapshot을 기록한다. 원천 큐와 로컬 파일은 수정·삭제하지 않으며, 같은 원천 큐 또는 대상 idempotency key의 반복 승인은 신규 원천·큐·감사를 중복 생성하지 않는다. 실행 명령과 전후 SQL 검증은 [보존 동기화 실패 무손실 전환](./legacy-sync-migration.md)을 따른다.

문서 최신 버전은 `documents.version_no`와 `document_versions.is_latest`를 기준으로 서버 최신 버전에 연결한다. 이미 서버에 같은 `version_no`가 있으면 SHA-256까지 일치할 때만 중복 업로드 없이 매핑을 복구한다. 현재 공개는 서버 승인 작업함이 최신 version·revision·file hash와 승인 ID를 사용해 직접 처리하며, 로컬 `published_version_no`를 먼저 바꾸거나 새 공개 큐를 만들지 않는다. 누적된 `document_publish/publish_document_version` 큐와 처리기는 삭제하지 않지만 승인 강제 기본값에서는 승인 ID가 없어 자동 공개할 수 없다. 상태 변경은 큐에 고정한 로컬 상태를 서버에 반영하며 `PUBLISHED` 진입은 공개 API만 수행한다. 태그 변경은 마지막 `server_tags_json`과 현재 로컬 태그를 비교한 추가·제거 delta와 canonical intent hash를 보존한다. 서버는 revision별 태그 집합을 기준으로 겹치지 않는 delta만 병합하고 WPF는 응답과 상세 read-back을 확인한 뒤 태그·문서·mapping·큐·이력을 한 SQLite transaction으로 저장한다.

FieldComment 검토 큐는 생성 시점 `field_comments.review_revision`을 `base_domain_revision`에 고정하고 안정된 큐 key를 서버 `mutationKey`로 보낸다. 서버 성공 응답의 증가한 revision을 로컬에 반영한 뒤에만 큐를 종결한다. 구 큐처럼 base revision이 NULL인 항목은 서버 상세에서 현재 revision을 읽어 요청 기준값으로 사용하되 중간 상태를 자동 생성하지 않는다.

보고서는 로컬 보고서 문서와 `report_sources`를 먼저 만든 뒤 서버 저장을 시도한다. 신규 큐는 source type/local ID/version/hash/relation 정렬값의 hash를 `source_set_hash`에 고정하고 안정된 큐 key를 서버 `idempotencyKey`와 `mutationKey` 양쪽에 보낸다. 서버 저장이 성공하면 응답 source 집합 hash를 재계산해 일치하는 경우에만 `server_report_id`, `server_document_id`, `server_version_id`, report revision·내용 hash·source 집합 hash와 `server_id_mappings`를 함께 남긴다. 실패하거나 hash가 다르면 `server_sync_queue`에 `report/register_report` 항목을 보존한다. 작업순서 보드/항목/이력은 로컬 큐 대상이 아니다. WPF 화면은 서버 snapshot과 `board_revision`으로 직접 변경하고, 로컬 테이블은 기존 기록과 오프라인 읽기 캐시/초안으로만 보존한다. 서버 미연결 또는 조회 실패 상태에서는 생성·항목 추가·순서·상태 확정을 허용하지 않는다.

controlled copy grant는 FastAPI 서버의 `controlled_copy_grants`에만 저장한다. WPF 로컬 SQLite에는 활성 grant 테이블이나 grant 토큰을 보존하지 않고 `server_id_mappings`로 서버 문서/버전을 찾은 뒤 즉시 발급·다운로드·SHA-256 검증하며, 실패를 `server_sync_queue`에 넣지 않는다. FastAPI 서버 DB와 WPF 로컬 DB는 서로 다른 파일이어야 하며, 이미 잘못 생성된 서버 grant 테이블은 DB 삭제 없이 `scripts/repair-wpf-controlled-copy-schema.py`로 보존 격리한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```
