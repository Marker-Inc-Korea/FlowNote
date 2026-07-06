# FlowNote 시스템 맵

## 실행 구성

```text
Windows WPF App
  -> local SQLite: data/local/flownote.local.sqlite
  -> local Files/: uploads, FieldComment attachments
  -> optional FastAPI sync through FLOWNOTE_API_BASE_URL

FastAPI Server
  -> SQLite: services/api/data/flownote.sqlite3
  -> local storage/: uploaded document and attachment files
  -> /api/v1 REST API
```

WPF 앱은 로컬 저장을 우선한다. 서버 URL과 Bearer token이 있으면 문서, 문서 버전/공개/상태, FieldComment, 첨부, 접근 로그, 보고서 저장 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 실패 상태를 남긴다. 보고서는 로컬 보고서 문서와 `report_sources`를 먼저 남긴 뒤 `server_sync_queue`의 `register_report` 항목으로 서버 `/api/v1/reports` 저장을 재시도한다.

## 주요 도메인

```text
UserAccount
  -> role
  -> UserGroup

DocumentFolder
  -> Document
      -> DocumentVersion
      -> DocumentTag
      -> FieldComment
      -> DocumentViewLog

FieldComment
  -> FieldCommentAttachment
  -> Notification
  -> ReportSource

WorkSequenceBoard
  -> WorkSequenceItem
  -> WorkSequenceChangeHistory
  -> WorkSequenceNotificationCandidate
  -> Notification

Report
  -> ReportSource
  -> generated Document

ServerSyncQueue
  -> server_id_mappings
```

## 문서와 버전

`Document`는 문서 메타데이터이고 `DocumentVersion`은 파일 개정 단위이다. 등록 직후 문서는 `WORKING` 상태이며, 공개하려면 특정 버전을 명시적으로 publish해야 한다.

WPF 로컬 DB는 공개 버전을 `documents.published_version_no`와 `document_versions.is_published`로 관리한다. FastAPI 서버는 `documents.published_version_id`와 `document_versions.is_published`로 관리한다.

서버-WPF 동기화에서는 로컬 큐 순서를 우선한다. 문서 최초 등록이 서버 ID를 받아야 문서 버전, FieldComment, 접근 로그가 후속 서버 ID에 연결된다. 공개는 해당 버전의 서버 버전 ID가 있어야 실행하고, 상태 변경은 현재 로컬 문서 상태를 서버에 반영한다.

## FieldComment

FieldComment는 문서 파일 개정이 아니라 현장 원천 기록이다. 새 WPF 코멘트는 `field_comments`에 저장되며 문서 버전을 증가시키지 않는다. 첨부 사진/파일은 `field_comment_attachments`에 별도로 저장된다.

## 작업순서

작업순서는 문서 폴더의 `작업지시서` 파일과 별개인 운영 보드이다. `work_sequence_boards`와 `work_sequence_items`가 현재 작업순서와 상태를 관리하고, 순서/상태 변경은 이력과 알림 후보를 만든다.

현재 단계의 서버-WPF 동기화 큐는 작업순서 보드/항목/이력을 대상으로 하지 않는다. 서버 작업순서 API는 직접 호출 스모크로 검증하고, WPF 보고서는 작업순서 항목/이력을 보고서 source로 연결한다.

## 보고서

보고서는 FieldComment, 문서, 작업순서 항목/이력을 근거로 수동 초안을 만들고 문서로 저장하는 최소 흐름이 구현되어 있다. WPF는 로컬 보고서 문서를 먼저 만들고 source를 `report_sources`에 보존한 뒤 `/api/v1/reports` 저장을 시도한다. 실패하면 `server_sync_queue`에 남기고, 성공하면 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`를 채운다. AI가 자동 작성하는 보고서는 아직 구현 범위가 아니다.

## 후속 연동

MES/ERP는 후속 연동 대상이다. 현재 코드는 내부 작업순서와 문서/FieldComment 기록을 먼저 안정적으로 축적하는 단계다.

후속 어댑터가 도입되더라도 초기 수동 입력 데이터와 같은 연결점을 사용한다. 외부 작업지시는 `work_records.work_order_no`, `work_records.external_system`, `work_records.external_ref_id`, `work_sequence_items.work_order_no`로 연결하고, 작업지시 문서는 `work_records.work_instruction_document_id`와 `work_sequence_items.document_id`로 연결한다. FieldComment와 보고서는 `work_record_id`와 `report_sources`를 통해 작업내역과 근거를 추적한다.

AI 관련 현재 구현은 외부 AI 호출이 아니라 서버 DB에서 `ai_search_candidates` 근거 후보를 재생성하고 품질을 점검하는 read model이다. 외부 AI 호출 기반 검색/작업 조언은 자동 의사결정 계층이 아니라 축적된 공개 문서, FieldComment, 작업순서 이력, 보고서 근거를 검색하고 요약하는 후속 계층부터 검토한다. 착수 기준은 [MVP 범위 문서](./mvp-scope.md#후속-계층-착수-기준)를 따른다.
