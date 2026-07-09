# FlowNote 시스템 맵

## 실행 구성

```text
Windows WPF App
  -> local SQLite: data/local/flownote.local.sqlite
  -> local Files/: uploads, FieldComment attachments
  -> local notification review
  -> optional FastAPI sync through FLOWNOTE_API_BASE_URL

Android Field App
  -> approved shop-floor tablet or rugged device
  -> document viewing, FieldComment, photos
  -> FastAPI sync through configured server URL

FastAPI Server
  -> SQLite: services/api/data/flownote.sqlite3
  -> local storage/: uploaded document and attachment files
  -> /api/v1 REST API
```

WPF 앱은 로컬 저장을 우선한다. 서버 URL과 Bearer token이 있으면 문서, 문서 버전/공개/상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 저장 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 실패 상태를 남긴다. 보고서는 로컬 보고서 문서와 `report_sources`를 먼저 남긴 뒤 `server_sync_queue`의 `register_report` 항목으로 서버 `/api/v1/reports` 저장을 재시도한다. 큐 재시도는 단순 생성 순서가 아니라 같은 문서 또는 보고서 근거 단위로 묶고, 선행 서버 ID가 필요한 항목은 보류로 분류해 서버 호출과 `attempt_count` 증가를 건너뛴다.

WPF 앱은 현재 로컬 `notifications` 테이블과 알림 창으로 문서, FieldComment, 작업순서 이벤트 알림을 확인하고 읽음 처리한다. 채널 생성, 채널 멤버 관리, 인수인계 수신 확인, 후속 조치 추적은 서버 채널/인수인계 모델이 추가된 뒤 WPF 감독 화면으로 확장한다.

Android 앱은 현장 단말 입력을 우선한다. 현장 작업자는 공개 문서 열람, QR/검색 기반 문서 접근, FieldComment와 사진 기록, 신호등식 상태 기록을 수행한다. 인수인계 작성/확인과 채널 알림 확인은 후속 채널/인수인계 서버 모델과 함께 확장한다. Android의 로컬 저장은 네트워크 불안정 구간의 임시 보관과 재전송을 위한 범위로 제한하고, 장기 기준 데이터는 FastAPI 서버에 남긴다.

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
  -> Notification (WPF local)
  -> ReportSource

WorkSequenceBoard
  -> WorkSequenceItem
  -> WorkSequenceChangeHistory
  -> WorkSequenceNotificationCandidate
  -> Notification (WPF local)

Report
  -> ReportSource
  -> generated Document

AISearchCandidate
  -> published DocumentVersion
  -> FieldComment
  -> WorkSequenceChangeHistory
  -> ReportSource

ServerSyncQueue
  -> server_id_mappings
```

## 문서와 버전

`Document`는 문서 메타데이터이고 `DocumentVersion`은 파일 개정 단위이다. 등록 직후 문서는 `WORKING` 상태이며, 공개하려면 특정 버전을 명시적으로 publish해야 한다.

WPF 로컬 DB는 공개 버전을 `documents.published_version_no`와 `document_versions.is_published`로 관리한다. FastAPI 서버는 `documents.published_version_id`와 `document_versions.is_published`로 관리한다.

서버-WPF 동기화에서는 같은 문서의 서버 ID 선행 조건을 우선한다. 재시도 큐는 문서 등록, 문서 버전, 공개, 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 순서로 처리한다. 문서 최초 등록이 서버 ID를 받아야 문서 버전, FieldComment, 접근 로그가 후속 서버 ID에 연결된다. 공개는 해당 버전의 서버 버전 ID가 있어야 실행하고, `PUBLISHED` 상태 변경은 공개 버전 매핑이 있어야 서버에 반영한다.

## FieldComment

FieldComment는 문서 파일 개정이 아니라 현장 원천 기록이다. 새 WPF 코멘트는 `field_comments`에 저장되며 문서 버전을 증가시키지 않는다. 첨부 사진/파일은 `field_comment_attachments`에 별도로 저장된다.

관리자 검토 화면은 FieldComment를 상태, 문서, 작성자, 태그, 기간으로 필터링하고 선택 항목의 정리 내용, 분석 내용, 상태를 수정한다. 첨부 사진/파일은 같은 화면의 첨부 목록에서 원본 파일명, 유형, 로컬 경로, 서버 첨부 ID로 추적한다. 검토 변경은 로컬 DB에 먼저 저장하고 서버가 연결되어 있으면 `/api/v1/field-comments/{comment_id}` PATCH로 반영하며, 실패하면 `server_sync_queue`의 `field_comment_review/update_field_comment_review` 항목으로 남긴다.

## 작업순서

작업순서는 루트의 `작업순서` 폴더에 둘 수 있는 문서와 별개인 운영 보드이다. `work_sequence_boards`와 `work_sequence_items`가 현재 작업순서와 상태를 관리하고, 순서/상태 변경은 이력과 알림 후보를 만든다.

현재 단계의 서버-WPF 동기화 큐는 작업순서 보드/항목/이력을 대상으로 하지 않는다. 서버 작업순서 API는 직접 호출 스모크로 검증하고, WPF 보고서는 작업순서 항목/이력을 보고서 source로 연결한다.

## 채널 알림과 인수인계

Windows와 Android의 알림은 장기적으로 개인 메신저가 아니라 업무 채널 모델로 다룬다. 채널은 라인, 설비, 공정, 작업조, 작업내역, 인수인계 같은 운영 단위에 연결된다. 사용자는 자신이 속한 채널의 문서 공개/변경, FieldComment 등록/검토 요청, 작업순서 변경, 인수인계 등록/확인 요청 알림을 받는다.

현재 구현된 알림은 WPF 로컬 `notifications`, 서버 작업순서 알림 후보(`work_sequence_notification_candidates`), FastAPI 공통 채널 모델(`notification_channels`, `notification_channel_members`, `channel_messages`)이다. WPF는 문서, FieldComment, 작업순서 이벤트 알림을 로컬 DB에 저장하고 읽음 처리한다. FastAPI는 채널 멤버십, 채널 메시지, 사용자별 알림 목록/읽음 처리, 인수인계와 수신 확인 API를 제공한다.

채널 메시지는 자유 대화를 무제한 보관하는 기능이 아니다. 각 메시지는 가능한 한 `document_id`, `field_comment_id`, `work_record_id`, `work_sequence_item_id`, `handover_id` 같은 원천 ID를 가져야 하며, 이후 보고서와 AI 검색 후보가 원문 근거로 역추적할 수 있어야 한다. 인수인계는 채널에 등록되는 업무 이벤트이며, 수신자는 확인, 보류, 후속 FieldComment 작성 같은 상태를 남길 수 있다.

초기 구현에서는 개인 DM, 사내 메신저 대체, 개인 휴대폰 알림 수집, GPS/근태 추적을 포함하지 않는다. 채널/인수인계 API는 서버 로그인 사용자, role, 채널 멤버십 기준으로 접근을 제한하며, 단말/클라이언트 승인 상태와 Windows/Android 전용 화면은 후속 클라이언트 구현에서 함께 적용한다.

## 보고서

보고서는 FieldComment, 문서, 작업순서 항목/이력을 근거로 수동 초안을 만들고 문서로 저장하는 최소 흐름이 구현되어 있다. WPF는 로컬 보고서 문서를 먼저 만들고 source를 `report_sources`에 보존한 뒤 `/api/v1/reports` 저장을 시도한다. 실패하면 `server_sync_queue`에 남기고, 성공하면 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`를 채운다. FieldComment 보고서 후보는 `SELECTED`, `REVIEWED`, `ANALYZED`를 우선 노출하고 `EXCLUDED`, `ARCHIVED`는 제외한다. AI가 자동 작성하는 보고서는 아직 구현 범위가 아니다.

## 후속 연동

MES/ERP는 후속 연동 대상이다. 현재 코드는 내부 작업순서와 문서/FieldComment 기록을 먼저 안정적으로 축적하는 단계다.

후속 어댑터가 도입되더라도 초기 수동 입력 데이터와 같은 연결점을 사용한다. 외부 작업지시는 `work_records.work_order_no`, `work_records.external_system`, `work_records.external_ref_id`, `work_sequence_items.work_order_no`로 연결하고, 작업지시 문서는 `work_records.work_instruction_document_id`와 `work_sequence_items.document_id`로 연결한다. FieldComment와 보고서는 `work_record_id`와 `report_sources`를 통해 작업내역과 근거를 추적한다.

AI 관련 현재 구현은 외부 AI 호출이 아니라 서버 DB에서 `ai_search_candidates` 근거 후보를 재생성하고 목록/품질을 점검하는 read model이다. WPF `AI 근거 후보 운영 점검` 화면은 서버 후보 재생성, source별 후보 수, 제외 사유와 운영 조치, FieldComment 검토 준비도, 후보 목록, 원천 추적값 복사를 제공한다. 운영 점검 흐름은 후보 재생성, source별 후보 수 확인, 제외 사유와 운영 조치 확인, 후보 row에서 원천 문서 버전/FieldComment/작업순서 이력/보고서 source로 역추적하는 순서다. FieldComment 검토 준비도는 분석/검토/선정 상태 100건 기준의 부족분을 먼저 보여주며, 이 수치가 부족하면 AI 답변 생성보다 FieldComment 검토와 보고서 source 정리를 우선한다. 외부 AI 호출 기반 검색/작업 조언은 자동 의사결정 계층이 아니라 축적된 공개 문서, FieldComment, 작업순서 이력, 보고서 근거를 검색하고 요약하는 후속 계층부터 검토한다. 착수 기준은 [MVP 범위 문서](./mvp-scope.md#후속-계층-착수-기준)를 따른다.
