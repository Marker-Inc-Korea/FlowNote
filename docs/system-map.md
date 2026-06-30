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

WPF 앱은 로컬 저장을 우선한다. 서버 URL과 Bearer token이 있으면 서버 API를 호출하고, 실패하면 `server_sync_queue`와 `activity_history`에 실패 상태를 남긴다.

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

## FieldComment

FieldComment는 문서 파일 개정이 아니라 현장 원천 기록이다. 새 WPF 코멘트는 `field_comments`에 저장되며 문서 버전을 증가시키지 않는다. 첨부 사진/파일은 `field_comment_attachments`에 별도로 저장된다.

## 작업순서

작업순서는 문서 폴더의 `작업지시서` 파일과 별개인 운영 보드이다. `work_sequence_boards`와 `work_sequence_items`가 현재 작업순서와 상태를 관리하고, 순서/상태 변경은 이력과 알림 후보를 만든다.

## 보고서

보고서는 FieldComment, 문서, 작업순서 항목/이력을 근거로 수동 초안을 만들고 문서로 저장하는 최소 흐름이 구현되어 있다. AI가 자동 작성하는 보고서는 아직 구현 범위가 아니다.

## 후속 연동

MES/ERP는 후속 연동 대상이다. 현재 코드는 내부 작업순서와 문서/FieldComment 기록을 먼저 안정적으로 축적하는 단계다.
