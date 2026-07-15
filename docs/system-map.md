# FlowNote 시스템 맵

이 시스템 맵은 2026-07-15 현재 실행 코드와 저장소 경계를 기준으로 한다. 후속 연동은 마지막 절에서만 예외로 표시한다.

## 실행 구성

```text
Windows WPF App
  -> local SQLite: data/local/flownote.local.sqlite
  -> local Files/: uploads, FieldComment attachments
  -> local notification review
  -> server account lifecycle/session management when server-authenticated
  -> optional FastAPI sync through FLOWNOTE_API_BASE_URL

Android Field App
  -> approved shop-floor tablet or rugged device
  -> device_id approved server login
  -> published document list/detail metadata, FieldComment, photos, signal input
  -> foreground channel notification polling and handover receipts
  -> local SQLite outbox for unstable network retry
  -> FastAPI sync through configured server URL

FastAPI Server
  -> SQLite: services/api/data/flownote.sqlite3
  -> local storage/: uploaded document and attachment files
  -> /api/v1 REST API
```

WPF 앱은 로컬 저장을 우선한다. 서버 URL과 Bearer token이 있으면 문서, 문서 버전/공개/상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 저장 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 실패 상태를 남긴다. 보고서는 로컬 보고서 문서와 `report_sources`를 먼저 남긴 뒤 `server_sync_queue`의 `register_report` 항목으로 서버 `/api/v1/reports` 저장을 재시도한다. 큐 재시도는 단순 생성 순서가 아니라 같은 문서 또는 보고서 근거 단위로 묶고, 선행 서버 ID가 필요한 항목은 보류로 분류해 서버 호출과 `attempt_count` 증가를 건너뛴다. 문서 버전과 FieldComment 첨부도 큐의 idempotency key를 서버 multipart 요청에 전달해 응답 유실 뒤 재시도가 중복 버전이나 파일을 만들지 않게 한다.

`작업내역`의 동기화 큐 화면은 각 row를 완료, 보존 구 형식, 선행 조건 대기, 수동 조치 필요, 재시도 가능의 운영 상태로 구분한다. 요약은 `SYNCED`가 아닌 큐 깊이, 그중 가장 오래된 `created_at` 기준 대기 시간, 최근 1시간 `SYNCED` 처리량, `FAILED` 진단 분포를 표시한다. 인증 만료와 서버 연결 실패·시간 초과는 뒤 항목도 같은 원인으로 연속 실패시키지 않도록 현재 재시도 묶음을 즉시 중단하고, 항목 자체의 검증·로컬 파일 오류는 실패를 기록한 뒤 다음 독립 항목을 계속 처리한다.

과거 구 `create` action과 FieldNote/첨부가 남은 FAILED 큐는 일반 재시도가 현재 계약으로 자동 해석하지 않는다. `FlowNote.Windows.SyncMigrationTool`이 먼저 SQLite read-only dry-run으로 전체 FAILED 큐를 배타적으로 분류하고 안정된 plan hash를 만든다. 운영자가 plan hash와 row ID를 명시해 승인하면 전환 가능한 항목만 현재 action의 별도 `PENDING` 큐로 만들고 `server_sync_migration_audit`에 원천 snapshot과 연결을 남긴다. 기존 큐, 원천 행과 파일은 수정·삭제하지 않는다.

WPF 앱은 로컬 `notifications` 테이블과 알림 창으로 문서, FieldComment, 작업순서 이벤트 알림을 확인하고 읽음 처리한다. 서버 URL과 로그인이 있으면 `채널함`, `채널 관리`, `인수인계 확인 현황` 화면에서 FastAPI 채널/인수인계 API를 직접 호출한다. 채널함은 내 채널, 사용자별 알림, 인수인계 목록을 조회하고 메시지 읽음, 내 receipt 상태 변경, 원천 링크 복사, 후속 FieldComment 생성을 수행한다. 주 창이 열려 있는 동안 `server_notification_cursors`의 서버 scope·사용자별 마지막 성공 cursor 다음 알림을 기본 15초 간격으로 조회하고, `server_notification_messages`의 `message_id`로 멱등 처리한 뒤 같은 트랜잭션에서 cursor를 전진시킨다. 연결 실패 시 최대 120초까지 backoff하며 401이면 cursor를 유지한 채 중단한다. 저장 row가 없는 사용자는 cursor 0부터 최대 100건씩 빠르게 따라잡고 한글 진행 상태를 표시한다. 서버 cursor 역행은 자동 복구하지 않고 polling을 중지하며 Core 서비스가 `admin`, `system-admin` role을 다시 확인한 경우에만 현재 scope·사용자의 cursor 초기화를 허용한다. 초기화 뒤에도 기존 처리 `message_id`는 보존해 재조회 부작용을 막는다. 채널 관리는 채널 생성, 멤버 추가/제외를 제공하고, 인수인계 확인 현황은 수신자별 receipt 상태 변경과 후속 FieldComment 생성을 제공한다. 서버 로그인한 `admin`, `system-admin`은 `사용자 관리` 화면에서 서버 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기를 수행한다. 로컬 로그인은 별도 로컬 계정 화면을 사용한다. `admin`, `system-admin`은 `승인 단말` 화면에서 서버 단말 목록·상세·마지막 접속을 조회하고 등록, 정보/상태 변경, 교체를 수행한다.

Android 앱은 현장 단말 입력을 우선한다. 현장 작업자는 승인된 `deviceId`로 로그인하고 공개 문서 목록/상세 메타데이터 조회, FieldComment와 사진 기록, 신호등식 상태 기록을 수행한다. 상세 화면은 제목·설명·상태·공개 버전 ID를 표시하고 FieldComment 입력에 문서/버전 ID를 연결하며, 문서 파일 본문을 내려받거나 렌더링하지 않는다. Activity가 전경인 동안 채널 알림을 기본 15초 간격으로 polling하고, 연결 실패 시 최대 120초까지 backoff한 뒤 사용자별 마지막 cursor부터 재개한다. 인수인계는 같은 알림 스트림과 서버 인수인계 API에서 조회하고 읽음 또는 수신확인을 남긴다. Android의 로컬 저장은 네트워크 불안정 구간의 FieldComment와 사진 첨부 임시 보관, 재전송, 서버 원천 ID 연결 범위로 제한하고, 장기 기준 데이터는 FastAPI 서버에 남긴다. outbox는 `PENDING`, `FAILED` 항목을 최대 12회 자동 시도하며 15초부터 지수 backoff를 적용해 최대 15분 간격으로 재전송한다. 로그인, 문서, 알림, 인수인계 API 실패는 서버 원문을 화면에 직접 표시하지 않고 연결 실패·시간 초과와 HTTP 상태를 현장 사용자가 조치할 수 있는 한글 안내로 변환한다.

## 주요 도메인

```text
UserAccount
  -> role
  -> UserGroup
  -> must_change_password / password_changed_at
  -> AuthSession
      -> TerminalDevice (approved Android device)

DocumentFolder
  -> Document
      -> DocumentVersion
      -> ControlledCopyGrant -> AuthSession + UserAccount + optional TerminalDevice
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

AISearchEvaluationRun
  -> AISearchEvaluationCase
  -> expected/actual AISearchCandidate snapshot
  -> excluded source and ranking snapshot

AIQuery (safety/audit skeleton, external call disabled by default)
  -> AIQueryEvidenceCandidate -> AISearchCandidate snapshot
  -> AIQueryCitation -> DocumentVersion | FieldComment | WorkSequenceChangeHistory | ReportSource
  -> AICallAttempt -> immutable AIPromptVersion
  -> AITransferApproval

ServerSyncQueue
  -> server_id_mappings
  -> ServerSyncMigrationAudit -> approved replacement ServerSyncQueue
```

`TerminalDevice`는 Android 현장 단말 승인 기준이며 `ACTIVE`, `INACTIVE`, `RETIRED` 상태를 갖는다. Android 로그인은 `ACTIVE` 단말만 허용하고 성공 시 마지막 접속 시각과 세션의 단말 ID를 남긴다. 비활성화, 폐기, 교체는 기존 활성 세션을 폐기하며 운영 변경은 `activity_history`로 추적한다.

## 문서와 버전

`Document`는 문서 메타데이터이고 `DocumentVersion`은 파일 개정 단위이다. 등록 직후 문서는 `WORKING` 상태이며, 공개하려면 특정 버전을 명시적으로 publish해야 한다.

WPF 로컬 DB는 공개 버전을 `documents.published_version_no`와 `document_versions.is_published`로 관리한다. FastAPI 서버는 `documents.published_version_id`와 `document_versions.is_published`로 관리한다.

허용 role의 제한 다운로드는 WPF 로컬 원본 복사가 아니라 서버 controlled copy를 사용한다. WPF가 현재 공개 버전의 티켓을 요청하면 서버는 공개 상태, 저장소 경계, 크기와 SHA-256을 검사하고 사용자·로그인 세션에 묶인 기본 60초 1회성 grant를 발급한다. 같은 Bearer 세션으로 한 번만 스트리밍하며 WPF는 저장 뒤 응답 SHA-256과 실제 파일을 다시 대조한다. 발급·허용·완료·실패·차단은 문서 접근 로그와 활동 이력으로 추적한다.

서버-WPF 동기화에서는 같은 문서의 서버 ID 선행 조건을 우선한다. 재시도 큐는 문서 등록, 문서 버전, 공개, 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 순서로 처리한다. 문서 최초 등록이 서버 ID를 받아야 문서 버전, FieldComment, 접근 로그가 후속 서버 ID에 연결된다. 공개는 해당 버전의 서버 버전 ID가 있어야 실행하고, `PUBLISHED` 상태 변경은 공개 버전 매핑이 있어야 서버에 반영한다.

## FieldComment

FieldComment는 문서 파일 개정이 아니라 현장 원천 기록이다. 새 WPF 코멘트는 `field_comments`에 저장되며 문서 버전을 증가시키지 않는다. 첨부 사진/파일은 `field_comment_attachments`에 별도로 저장된다.

관리자 검토 화면은 FieldComment 원천을 읽기 전용으로 표시하고 상태, 문서, 작성자, 담당자, 태그, 라인, 설비, 공정, 오류 유형, 기간, 오래된 NEW, 첨부와 보고서 연결 여부로 필터링한다. 관리자 해석 영역의 정리·분석 내용, 담당자, 검토 기한, 상태와 필수 전이 사유를 수정하고 다중 선택 항목을 순서대로 로컬 저장·개별 동기화한다. 첨부 사진/파일은 같은 화면의 첨부 목록에서 원본 파일명, 유형, 로컬 경로, 서버 첨부 ID로 추적한다. WPF 검토 변경은 로컬 DB에 먼저 저장하고 서버가 연결되어 있으면 각 항목을 `/api/v1/field-comments/{comment_id}` PATCH로 반영하며, 실패하면 `server_sync_queue`의 `field_comment_review/update_field_comment_review` 항목으로 남긴다. FastAPI의 별도 `/api/v1/field-comments/bulk-review`는 요청당 최대 200건을 한 트랜잭션으로 검증·저장한다. 원천 hash를 포함한 전후 snapshot 감사와 오래된 NEW·근거 부족 SELECTED·원천 누락 보고서 품질 작업함/지표도 서버 API에서 제공한다.

## 작업순서

작업순서는 루트의 `작업순서` 폴더에 둘 수 있는 문서와 별개인 운영 보드이다. `work_sequence_boards`와 `work_sequence_items`가 현재 작업순서와 상태를 관리하고, 순서/상태 변경은 이력과 알림 후보를 만든다.

현재 단계의 서버-WPF 동기화 큐는 작업순서 보드/항목/이력을 대상으로 하지 않는다. 서버 작업순서 API는 직접 호출 스모크로 검증하고, WPF 보고서는 작업순서 항목/이력을 보고서 source로 연결한다.

## 채널 알림과 인수인계

Windows와 Android의 알림은 장기적으로 개인 메신저가 아니라 업무 채널 모델로 다룬다. 채널은 라인, 설비, 공정, 작업조, 작업내역, 인수인계 같은 운영 단위에 연결된다. 사용자는 자신이 속한 채널의 문서 공개/변경, FieldComment 등록/검토 요청, 작업순서 변경, 인수인계 등록/확인 요청 알림을 받는다.

현재 구현된 알림은 WPF 로컬 `notifications`, `server_notification_cursors`, `server_notification_messages`, 서버 작업순서 알림 후보(`work_sequence_notification_candidates`), FastAPI 공통 채널 모델(`notification_channels`, `notification_channel_members`, `channel_messages`)이다. WPF는 문서, FieldComment, 작업순서 이벤트 알림을 로컬 DB에 저장하고 읽음 처리하며, 서버 채널 화면에서는 내 채널/메시지/인수인계를 조회하고 읽음/수신 확인을 남긴다. Windows와 Android는 전경에서 `/api/v1/notifications?afterId={cursor}`를 polling하고 응답 처리가 끝난 뒤에만 cursor를 전진시킨다. Android는 사용자별 cursor를 `SharedPreferences`에 보존하고 현재 사용자 receipt를 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`로 변경한다. WPF는 서버 scope·사용자별 cursor와 처리한 `message_id`를 SQLite에 영구 보존한다. FastAPI는 채널 멤버십, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음 처리, 인수인계와 수신 확인 API를 제공한다.

채널 메시지는 자유 대화를 무제한 보관하는 기능이 아니다. 각 메시지는 가능한 한 `document_id`, `field_comment_id`, `work_record_id`, `work_sequence_item_id`, `handover_id` 같은 원천 ID를 가져야 하며, 이후 보고서와 AI 검색 후보가 원문 근거로 역추적할 수 있어야 한다. 인수인계는 채널에 등록되는 업무 이벤트이며, 수신자는 확인, 보류, 후속 FieldComment 작성 같은 상태를 남길 수 있다.

초기 구현에서는 개인 DM, 사내 메신저 대체, 개인 휴대폰 알림 수집, GPS/근태 추적을 포함하지 않는다. 채널/인수인계 API는 서버 로그인 사용자, role, 채널 멤버십 기준으로 접근을 제한한다. Android는 `terminal_devices` 승인 상태를 로그인 단계에서 검증하고, Windows는 관리자/감독 화면 중심으로 같은 서버 채널 데이터를 공유한다.

## 보고서

보고서는 FieldComment, 문서, 작업순서 항목/이력을 근거로 수동 초안을 만들고 문서로 저장하는 최소 흐름이 구현되어 있다. WPF는 로컬 보고서 문서를 먼저 만들고 source를 `report_sources`에 보존한 뒤 `/api/v1/reports` 저장을 시도한다. 실패하면 `server_sync_queue`에 남기고, 성공하면 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`를 채운다. FieldComment 보고서 후보는 `SELECTED`, `REVIEWED`, `ANALYZED`를 우선 노출하고 `EXCLUDED`, `ARCHIVED`는 제외한다. AI가 자동 작성하는 보고서는 아직 구현 범위가 아니다.

## 후속 연동

MES/ERP는 후속 연동 대상이다. 현재 코드는 내부 작업순서와 문서/FieldComment 기록을 먼저 안정적으로 축적하는 단계다.

후속 어댑터가 도입되더라도 초기 수동 입력 데이터와 같은 연결점을 사용한다. 외부 작업지시는 `work_records.work_order_no`, `work_records.external_system`, `work_records.external_ref_id`, `work_sequence_items.work_order_no`로 연결하고, 작업지시 문서는 `work_records.work_instruction_document_id`와 `work_sequence_items.document_id`로 연결한다. FieldComment와 보고서는 `work_record_id`와 `report_sources`를 통해 작업내역과 근거를 추적한다.

AI 관련 현재 구현은 외부 AI 호출이 아니라 서버 DB에서 `ai_search_candidates` 근거 후보를 재생성하고 목록/품질을 점검하는 read model이다. 공개 문서 후보는 삭제되지 않은 공개 문서 버전만 사용하고, 보고서 source도 실제 원천을 다시 확인한다. 특히 `DOCUMENT` 원천이 삭제 상태이거나 `deleted_at`이 설정되어 있으면 보고서가 남아 있어도 검색 후보로 만들지 않는다. WPF `AI 근거 후보 운영 점검` 화면은 서버 후보 재생성, source별 후보 수, 제외 사유와 운영 조치, FieldComment 검토 준비도, 후보 목록, 원천 추적값 복사를 제공한다. 운영 점검 흐름은 후보 재생성, source별 후보 수 확인, 제외 사유와 운영 조치 확인, 후보 row에서 원천 문서 버전/FieldComment/작업순서 이력/보고서 source로 역추적하는 순서다. FieldComment 검토 준비도는 분석/검토/선정 상태 100건 기준의 부족분을 먼저 보여주며, 이 수치가 부족하면 AI 답변 생성보다 FieldComment 검토와 보고서 source 정리를 우선한다.

외부 provider 착수 전 회귀 흐름은 질문 ground-truth → 권한을 반영한 후보 순위 → 기대 candidate/source/version/trace ID 비교 → 원천 URI 확인 → 재생성 전후 ID/content hash와 순위 비교 순서다. 실행과 케이스 snapshot은 공통 SQLite에 누적하며, 삭제·비공개·보관/제외·사라진 보고서 원천·권한 없는 채널은 부정 근거로 기록한다. 근거가 없는 질문은 답변 생성 대상이 아니라 `INSUFFICIENT_EVIDENCE`로 고정한다.

외부 AI 1단계는 위 read model과 분리된 후속 쓰기 흐름이다. 현재 구현은 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`를 기본값으로 두고, 보고서 작성 role, 허용 목적, 고객·현장·provider·model 승인, 승인 프롬프트, 원천 상태, 작성자 role, 채널 멤버십, 승인 source type, 민감정보 정책과 응답 인용 ID를 검사한다. provider 중립 adapter 뒤에서 JSON 구조·크기·중복·prompt injection과 claim/summary의 규칙 기반 의미 일치를 검사하고, 호출 전후 원천·권한·승인이 달라지면 결과를 폐기한다. 적격·제외 후보를 원문 없이 질의 시점 snapshot으로 남기고, 근거 없음·상충·최신성 불명·낮은 확신은 정상 `INSUFFICIENT_EVIDENCE`로 종료한다. 결과는 작업순서·문서 상태·보고서 승인·설비를 변경하지 않는다.

외부 AI 운영 제어면은 `system-admin` 전용 `/api/v1/ai-operations`와 WPF `AI 운영` 화면으로 연결된다. 전송 승인은 고객·현장·provider·model·목적·source type과 만료 시각을 고정하고 생성·철회를 감사한다. 프롬프트는 새 불변 버전을 만든 뒤 `DRAFT → REVIEWED → APPROVED → ACTIVE → RETIRED` 순서로 관리하며 목적별 새 버전을 활성화하면 이전 활성 버전을 폐기한다. 전역/현장 정책은 kill switch, 일일 요청·동시성·timeout·비용 한도, 질의·응답·감사 보존 기간과 감사 CSV 허용 여부를 관리한다. 질의 감사는 원문 없이 상태·차단 코드·근거·인용·호출 메타데이터를 보여준다. 서버 lifespan 스케줄러와 `system-admin` 즉시 실행 API는 같은 만료 처리를 사용해 질의 payload를 비식별화하고 응답 원문을 삭제하면서 hash와 참조·처리 감사를 보존한다. provider 자격증명은 환경/비밀 저장소에만 두며 API와 화면은 설정 여부만 노출한다.

provider 경계는 정제 질의, 최소 발췌, candidate/source/version/trace ID, content hash, 순위, prompt version과 허용 출력 형식만 받는다. fake/recording adapter가 기본 검증 경로이고 generic JSON 네트워크 adapter는 명시적 `test` scope에서만 생성된다. 권한 없거나 상태가 바뀐 원천, 전송 금지 정보는 경계 DTO에 포함되지 않는다. 데이터 모델은 [데이터 모델](./data-model.md#외부-ai-질의와-호출-로그-안전장치)와 [외부 AI 운영·보존 모델](./data-model.md#외부-ai-운영보존-모델), API 계약과 테스트 기준은 [API 문서](./api.md#외부-ai-근거-검색과-요약-안전장치)와 [외부 AI 운영 API](./api.md#외부-ai-운영-api), 전송 승인은 [보안 문서](./security.md#외부-ai-전송과-운영자-승인)를 따른다. 착수 기준은 [MVP 범위 문서](./mvp-scope.md#후속-계층-착수-기준)를 따른다.
