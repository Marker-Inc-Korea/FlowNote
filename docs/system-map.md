# FlowNote 시스템 맵

이 시스템 맵은 2026-08-04 현재 실행 코드와 저장소 경계를 기준으로 한다. 서버 복구 경계 manifest/reconciliation은 구현되었고 수렴 경계의 나머지 미구현 항목은 `목표 계약`으로, 후속 외부 연동은 마지막 절에서 구분한다.

## 실행 구성

```text
Windows WPF App
  -> local SQLite: data/local/flownote.local.sqlite
  -> local Files/: uploads, FieldComment attachments
  -> role-priority first tasks, document search/status filter
  -> permission guidance and local-preservation sync status
  -> local notification review
  -> server account lifecycle/session management when server-authenticated
  -> optional FastAPI sync through FLOWNOTE_API_BASE_URL

Android Field App
  -> approved shop-floor tablet or rugged device
  -> device_id approved server login
  -> published document list/detail metadata, FieldComment, photos, signal input
  -> foreground channel notification polling with processed message ledger
  -> handover create, acknowledge/hold and source-linked follow-up FieldComment
  -> encrypted local SQLite outbox for FieldComment, photo and handover workflow retry
  -> FastAPI sync through configured server URL

FastAPI Server
  -> SQLite: services/api/data/flownote.sqlite3
  -> local storage/: uploaded document and attachment files
  -> /api/v1 REST API
```

FastAPI 서버 SQLite와 WPF 로컬 SQLite는 서로 대체하거나 공유하는 파일이 아니다. 같은 이름의 문서 테이블도 서버는 `document_versions.version_id`, WPF는 로컬 `id`와 문서별 `version_no`를 기준으로 하므로 각 프로세스가 자기 DB만 초기화해야 한다. FastAPI는 기존 WPF 테이블 형태를 감지하면 `Base.metadata.create_all()` 전에 시작을 거부한다.

WPF 앱은 로컬 저장을 우선한다. 서버 URL과 Bearer token이 있으면 문서, 문서 버전/상태/태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 저장 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 실패 상태를 남긴다. 새 문서 공개는 예외다. 현재 UI는 서버 승인 작업함에서 최신 version·revision·file hash를 고정해 검토를 요청하고 승인 ID로 직접 공개하며, 로컬 선공개나 새 공개 큐를 만들지 않는다. 누적된 구 공개 큐와 처리기는 삭제하지 않지만 승인 강제 기본값에서는 승인 ID가 없어 자동 공개할 수 없다. 태그 큐는 마지막 서버 revision·태그 집합 대비 추가/제거와 canonical intent hash를 보내고, 서버는 revision별 태그 snapshot으로 비경합 delta만 병합한다. 같은 태그의 반대 방향 변경과 비활성·삭제 태그는 자동으로 덮어쓰지 않는다. FieldComment 검토 큐는 base review revision과 mutation key를, 첨부는 부모 comment ID와 파일 SHA-256을 보낸다. 보고서는 초안 생성 때 서버에서 선택 원천의 상태와 version/revision/hash를 검증해 snapshot을 먼저 고정한다. 이 검증을 통과한 뒤 로컬 보고서 문서와 `report_sources`를 남기고 source 집합 hash를 큐에 고정하며, 이후 서버 저장이 실패하면 `register_report` 항목으로 `/api/v1/reports` 저장을 재시도한다. 성공 응답의 source 집합을 다시 hash하고 report revision·내용/source 집합 hash를 로컬에 보존한 경우에만 종결한다. 큐 재시도는 같은 문서 또는 보고서 근거 단위로 묶고, 선행 서버 ID가 필요한 항목은 보류로 분류해 서버 호출과 `attempt_count` 증가를 건너뛴다. 재전송 가능한 mutation은 같은 key와 의도를 유지해 응답 유실 뒤에도 중복 버전, revision 또는 감사 이력을 만들지 않는다.

WPF 메인 화면은 로그인 역할에 맞춘 첫 업무 3개를 기존 메뉴·창과 같은 권한 검사 경로로 연결한다. 현재 역할 구분은 관리자, 반장, 조장, 작업자이며 문서 찾기, 인수인계, 작업판, 채널·알림, 코멘트 검토, 보고서 근거 선정, 동기화·충돌 확인을 우선순위에 맞춰 보여준다. 문서 검색은 현재 폴더의 파일명·제목·태그·사용자·최근 코멘트를 대상으로 하고, 상태 필터와 함께 폴더 이동이나 목록 갱신 뒤에도 유지된다. 권한이 없는 기능은 필요한 역할과 현장 관리자 문의 방법을 안내한다. 하단 동기화 상태는 대기·실패/충돌·보류 건수, 로컬 데이터와 원본 파일의 보존 여부, `이력 > 동기화 큐`에서 확인할 다음 조치를 색상에 의존하지 않고 표시한다.

`작업내역`의 동기화 큐 화면은 각 row를 완료, 보존 구 형식, 선행 조건 대기, 수동 조치 필요, 재시도 가능의 운영 상태로 구분한다. 전체 보존 건수는 `PENDING`, `FAILED`/`CONFLICT`, `SYNCED`, `DISCARDED`를 모두 세며, 서버본 유지로 종결한 `DISCARDED`는 삭제하지 않되 처리 대기 깊이에서는 제외한다. 요약은 `SYNCED`와 `DISCARDED`가 아닌 큐 깊이, 그중 가장 오래된 `created_at` 기준 대기 시간, 최근 1시간 `SYNCED` 처리량, `FAILED` 진단 분포를 표시한다. 인증 만료와 서버 연결 실패·시간 초과는 뒤 항목도 같은 원인으로 연속 실패시키지 않도록 현재 재시도 묶음을 즉시 중단하고, 항목 자체의 검증·로컬 파일 오류는 실패를 기록한 뒤 다음 독립 항목을 계속 처리한다.

과거 구 `create` action과 FieldNote/첨부가 남은 FAILED 큐는 일반 재시도가 현재 계약으로 자동 해석하지 않는다. `FlowNote.Windows.SyncMigrationTool`이 먼저 SQLite read-only dry-run으로 전체 FAILED 큐를 배타적으로 분류하고 안정된 plan hash를 만든다. 운영자가 plan hash와 row ID를 명시해 승인하면 전환 가능한 항목만 현재 action의 별도 `PENDING` 큐로 만들고 `server_sync_migration_audit`에 원천 snapshot과 연결을 남긴다. 기존 큐, 원천 행과 파일은 수정·삭제하지 않는다.

## 로컬 우선 데이터와 서버 권위 원천의 수렴 경계

아래 표는 새 동기화 작업이 따라야 하는 단일 운영 계약이다. `로컬 원천`은 서버 확인 전까지 삭제할 수 없는 입력·파일·큐를 뜻하고 `서버 권위`는 두 WPF 인스턴스, Android, AI 검색과 보고서가 최종 판정에 사용하는 값이다. 공통 mutation receipt와 versioned migration은 문서 승인 흐름을 추가한 `0003_document_approval_workflow`까지 구현되었으며 아직 코드에 없는 계약만 목표로 구분한다. 각 행의 검증을 통과하기 전에는 다중 WPF 쓰기를 허용하지 않는다.

| 대상 | 로컬 원천과 방향 | 서버 권위·동시성 키 | 멱등 키와 충돌 | 종결·수렴 조건 |
| --- | --- | --- | --- | --- |
| 문서 등록 | WPF 문서 메타데이터·최초 파일 → 서버 | `document_id`, `revision`, `latest_version_id`, 파일 SHA-256 | 안정된 문서 등록 key. 같은 key의 핵심 메타/hash 차이는 `IDEMPOTENCY_KEY_REUSED` | 서버 문서/버전 ID, revision, hash를 같은 로컬 transaction에서 매핑하고 큐 `SYNCED` |
| 문서 버전 | WPF 버전 파일 → 서버 | 문서 revision, 기준 latest version ID, 서버 배정 `version_no` | 버전 key+파일 hash. 기준 불일치는 `STALE_REVISION`/`STALE_BASE_VERSION`, hash 불일치는 `FILE_HASH_MISMATCH` | 서버 version ID·revision·hash read-back과 로컬 원천 hash가 모두 일치 |
| 문서 검토·공개 | WPF 승인 작업함 → 서버 직접 호출. 로컬 선공개·신규 공개 큐 없음 | 승인 ID, exact version·문서 revision·file hash, `published_version_id` | 요청·결정·공개·취소별 mutation key. stale version/revision/hash와 역할 분리 위반은 서버에서 거부 | 승인 projection·append-only event와 서버 공개 포인터를 다시 읽어 확인. 구 공개 큐는 별도 호환 이력으로 보존 |
| 문서/버전 상태 | WPF 명시 mutation → 서버, 이후 서버 snapshot → WPF | 문서 revision, 문서·버전 상태와 version hash | 요청별 안정 key와 base revision. stale/base/hash/공개본/삭제 경쟁은 `CONFLICT` | 자동 덮어쓰기 없이 서버 snapshot과 사용자 선택을 보존하고, 확정 응답을 로컬 transaction에 반영 |
| 문서 태그 | WPF 추가/제거 delta → 서버, 권위 집합 → WPF | 문서 revision, `document_tag_revisions`, 현재 활성 태그 집합 | mutation key+canonical intent hash. 비경합 delta만 병합하고 `TAG_MERGE_CONFLICT`, `TAG_UNAVAILABLE`은 사용자 판단 | revision·전체 태그·공개 포인터·최신 version/hash를 문서·태그·mapping·큐·감사에 한 transaction으로 반영 |
| FieldComment 원천 | WPF/Android 불변 입력 → 서버 | 서버 `comment_id`, 원천 hash, 연결 document/version ID | 원천 생성 key. 같은 key의 원천/연결 hash 차이는 `IDEMPOTENCY_KEY_REUSED` | 서버 comment ID·원천 hash·연결 ID 매핑 확인. 원천은 이후 수정·삭제하지 않음 |
| FieldComment 검토 | WPF 검토 mutation → 서버 | `review_revision`과 원천 hash. 서버가 상태·담당·기한·정리·분석의 권위 원천 | mutation key+`baseReviewRevision`; `FIELD_COMMENT_STALE_REVIEW_REVISION`, `IDEMPOTENCY_KEY_REUSED` | 서버 검토 snapshot과 증가한 revision을 로컬에 반영한 뒤 `SYNCED`; 자동 단계 보간 금지 |
| FieldComment 첨부 | 로컬 파일 → 서버 | 서버 attachment ID, 부모 comment ID, file object hash | 첨부 key+`parentCommentId`+`fileSha256`; `ATTACHMENT_PARENT_MISMATCH`, `ATTACHMENT_FILE_HASH_MISMATCH`, `IDEMPOTENCY_KEY_REUSED` | 서버 attachment/file hash를 확인하고 매핑. 로컬 파일은 보존 정책 전까지 유지 |
| 접근 로그 | WPF append-only 이벤트 → 서버 | 서버 log ID와 이벤트 payload hash | 시작·종료·차단 이벤트별 key; 동일 key payload 차이는 `IDEMPOTENCY_KEY_REUSED` | 서버 log ID 매핑 1개. 유실 응답 재시도에도 서버 row 1개 |
| 보고서와 source 집합 | WPF 보고서 파일/본문과 source snapshot → 서버 | 서버 report ID·`report_revision`, 생성 문서/버전 ID, `content_hash_sha256`, `source_set_hash_sha256`와 source별 ID/version/hash | mutation key와 선택적 base revision/content/source-set hash; `REPORT_STALE_REVISION`, `REPORT_SOURCE_STALE_OR_ORPHAN`, 두 `*_HASH_MISMATCH`, `IDEMPOTENCY_KEY_REUSED` | 서버는 report·생성 document/version·모든 source·receipt를 한 transaction에 저장. WPF는 응답 source-set hash를 재계산하고 revision/hash를 로컬에 보존한 뒤 종결 |
| 작업순서 보드·항목 | WPF가 서버 API를 직접 호출. 로컬 테이블은 초안/캐시·기존 기록만 보존 | 서버 `board_revision`, 항목 ID·순서·상태 | mutation key+`baseBoardRevision`; `WORK_SEQUENCE_STALE_REVISION`, `IDEMPOTENCY_KEY_REUSED` | 서버가 보드 mutation과 change history를 한 transaction으로 저장하고 새 revision 반환. 로컬 큐 없음 |
| 작업순서 이력 | 클라이언트가 별도 생성하지 않고 서버 mutation에서 파생 | 서버 append-only `change_id`, board revision | 부모 mutation key에서 1회 생성 | mutation 1건당 의미상 이력 1건, orphan 0건 |
| Android 인수인계 | Android 암호화 outbox → 서버 | 서버 `handover_id`, 연결 채널·원천·수신자 receipt, 승인 세션의 `device_id` | `android:{deviceId}:handover:{localId}`. 같은 키의 요청 내용이 다르면 `IDEMPOTENCY_KEY_REUSED` | 서버가 인수인계·채널 메시지·receipt를 한 transaction에 한 번만 저장하고 기존 `handover_id`를 재전송 응답에 반환 |
| Android 인수인계 확인·보류 | Android 암호화 outbox → 서버 receipt | 기존 `receipt_id`와 `ACKNOWLEDGED` 또는 `FOLLOW_UP_REQUIRED` 상태 | 같은 receipt 공개 ID와 동일 payload를 반복 갱신 | 서버 receipt 한 행만 갱신하고 Windows 감독 화면의 미확인·후속 인원 집계에 반영 |
| Android 인수인계 후속 FieldComment | Android 암호화 outbox → FieldComment → 채널 알림 | 서버 `comment_id`, 인수인계·업무 원천·채널 연결 | `handover-follow-up:{digest}`와 같은 채널·코멘트의 `FIELD_COMMENT_EVENT` 재사용 | 코멘트 저장 뒤 알림만 실패하면 `comment_id`를 보존하고 알림만 재시도 |
| 알림 cursor | 서버 → WPF/Android | 서버 scope·user별 high-water cursor와 공개 `message_id` | `message_id` 유일 처리. cursor 역행은 `SERVER_EPOCH_CHANGED` 복구 절차 | WPF는 처리 row와 cursor를 한 transaction에 저장하고, Android는 scope별 처리 원장 기록 뒤 cursor를 전진 |

operation key가 있는 문서 권위 변경, FieldComment 검토, 보고서 상태 전이와 작업순서 변경은 도메인 receipt를 유지하면서 공통 `SyncMutationReceipt`와 `AuditEventEnvelope`를 연결한다. 성공 시 업무 변경·도메인 receipt·공통 두 행을 한 transaction에 저장한다. 문서 상태, FieldComment 검토, 보고서 상태 전이, 작업순서 항목 상태의 거부·충돌은 업무 변경을 rollback한 뒤 공통 결과만 확정해 같은 요청의 재시도가 같은 HTTP 결과로 수렴하도록 한다. 기존 `activity_history`는 백필하지 않으며 `/api/v1/audit-events`에서 누락 필드를 명시한 이전 형식으로 함께 조회한다.

WPF `변경 이력`은 `/api/v1/change-history` read model을 사용해 문서, FieldComment, 보고서, 작업순서와 공통 동기화 mutation을 한 목록에 표시한다. `audit_event_envelopes`가 권위 원천이며 read model은 저장하지 않는다. 첫 페이지의 event ID 상한을 커서에 고정하고 조치 필요·문제 유형 우선순위·시간 순으로 읽어 pagination 중 신규 event가 섞이지 않게 한다. 충돌, 실패, 미연결 mutation, 필수 감사 필드 누락과 권한 거부 뒤 revision 변경을 먼저 표시하고 영향, 현재 상태, 담당자, 다음 행동을 함께 계산한다. 문서 충돌은 로컬 이력의 충돌 조치, FieldComment는 검토, 보고서는 보고서, 작업순서는 작업판 화면으로 연결하며 원본 event envelope는 같은 창에서 다시 조회한다. 목록 합계와 상세는 동일한 역할·채널 멤버십 정책을 사용하고 권한 밖 대상은 `404`와 목록 제외로 존재를 숨긴다.

재시도기는 같은 aggregate를 직렬화하고 다음 순서로 처리한다.

```text
문서 등록
  -> 문서 버전
  -> 누적 구 공개 큐(호환 경로)
  -> 문서/버전 상태와 태그
  -> FieldComment 원천
  -> FieldComment 검토
  -> FieldComment 첨부
  -> 접근 로그
  -> 보고서와 source 집합
```

`503`, 연결 실패, timeout과 응답 유실은 현재 row를 `FAILED`로 보존하고 `Retry-After`가 있으면 우선 적용하며, 없으면 5초부터 5분까지 지수 backoff와 jitter를 적용한다. 인증 401/403은 묶음을 중단한다. 선행 매핑 누락은 서버 호출과 `attempt_count` 증가 없이 보류한다. 409, 로컬 파일/hash 불일치와 계약 오류는 자동 재시도하지 않고 `CONFLICT` 또는 보존 `FAILED`로 남긴다. `SYNCED`와 관리자가 서버본 유지 사유를 남긴 `DISCARDED`만 종결 상태이며 어느 상태에서도 원천·큐·감사 row를 자동 삭제하지 않는다.

### 서버 복구·초기화 뒤 재검증

서버 초기화는 `server_identity` singleton row가 없을 때 `srv-` 접두의 난수 `server_instance_id`, `server_epoch = 1`, schema/API contract 1을 만든다. 운영자가 `POST /api/v1/sync/server-epoch/increment`를 호출할 때만 현재 코드가 epoch를 증가시킨다. `/api/v1/sync/manifest`와 `/api/v1/health/sync-manifest`는 이 값과 `channel_messages.id`의 high-water cursor를 제공한다. 별도 PC 복구 장애 실기에서는 환경에 고정한 장애 코드, 독립 pilot run ID, backup set ID, 복구 승인 ID, 담당자 역할 ID와 `safe_convergence=false`도 제공한다. WPF는 정규화한 서버 URL별로 이 메타데이터와 binding을 저장한다. 최초 binding은 `ACTIVE`지만, 명시적 복구 장애가 있거나 다른 URL binding이 이미 있거나 저장한 instance/epoch가 달라지거나 high-water cursor가 로컬 cursor보다 낮으면 일반 전송과 polling을 즉시 멈추고 `RECONCILIATION_REQUIRED`로 전환한다. API contract 1이 서버 지원 범위에 없거나 manifest가 유효하지 않아도 자동 전송을 시작하지 않는다.

관리자 재검증은 판정 전에 기존 cursor, `server_id_mappings`, 모든 상태의 큐를 삭제하거나 변경하지 않는다. WPF `작업내역 > 서버 재결합`은 `server_sync_queue` 전체와 기존 mapping에서 로컬 entity ID/version, idempotency key, 이전 서버 문서/버전 ID, 선택적 파일 hash를 모아 최대 10,000건의 run을 만든다. 서버는 `document`, `document_version`, `field_comment`, `field_comment_attachment`, `document_access_log`, `report`를 지원하며 각 항목을 다음 중 하나로 분류한다.

- `CONFIRMED / REBOUND`: 같은 idempotency key와 제공된 hash가 일치하면 새 server ID/revision/hash로 매핑을 재결합하고 해당 큐를 `SYNCED`로 종결한다.
- `ABSENT / REQUEUE`: 같은 key의 서버 row가 없으면 해당 큐의 이전 서버 ID를 비우고 `PENDING`으로 되돌려 같은 key로 재전송한다.
- `DIVERGED / CONFLICT`: 지원하지 않는 entity, 비교 hash 부재 또는 불일치이면 해당 큐를 `DISCARDED`로 종결하되 `RECONCILIATION_DIVERGED`와 상세·해결자·시각을 보존한다.

관리자는 화면의 전 항목과 승인 사유를 확인한다. 서버가 모든 조치가 제안값과 일치하는지 검증하고 run·항목 해결 감사와 활동 이력을 저장한 뒤, WPF가 한 transaction에서 큐·mapping·binding을 적용한다. 그때만 현재 서버 scope의 모든 알림 cursor를 0으로 되돌리고 초기 따라잡기를 재개하며 기존 처리 `message_id`는 보존한다. 적용 직후 `PENDING` 큐 재전송도 다시 실행한다. 수렴 완료는 비종결 큐 0건, 동일 idempotency key의 서버 중복 row 0건, mapping의 orphan 0건, 문서 공개 포인터·보고서 source/version·파일 hash 일치와 cursor 재추적 완료를 모두 만족할 때다.

### 수렴 검증 게이트

자동 통합 검증은 빈 임시 DB 대신 보존 대상 검증 DB의 복사본을 사용하고, 원본과 실행 산출물을 삭제하지 않는다. 두 WPF client instance ID와 한 서버를 사용해 같은 aggregate에 다음 순서로 장애를 주입한다.

1. 두 WPF가 같은 문서 revision에서 서로 다른 새 버전·상태·공개 요청을 만들고 한쪽만 성공하는지 확인한다.
2. 같은 FieldComment에 동시 검토를 요청하고 stale review가 409로 보존되는지, 첨부 응답을 유실한 뒤 같은 key 재시도에서 서버 첨부가 한 건인지 확인한다.
3. 보고서 source를 선택한 뒤 원천 version/hash를 바꾸어 stale 저장을 차단하고, 고정된 source snapshot 저장의 report/document/version/source 매핑을 확인한다.
4. 작업순서 같은 board revision에서 순서 변경과 상태 변경을 경쟁시켜 하나만 성공하고 성공 mutation의 이력이 정확히 한 건인지 확인한다.
5. 각 단계에 503, 응답 유실과 WPF 재시작을 주입한 뒤 재시도하고, server DB 복구/초기화로 epoch를 바꾼 뒤 mapping reconciliation과 cursor 0 재추적을 수행한다.

각 경계에서 WPF 2개와 서버 DB의 row count, revision, `published_version_id`, report source ID/version/hash, file hash, idempotency key를 정렬 CSV/JSON과 SHA-256으로 남긴다. 최종 판정 SQL은 `PRAGMA quick_check = ok`, 빈 `foreign_key_check`, idempotency/mutation key 중복 0건, published pointer orphan 0건, report source orphan 0건, mapping orphan 0건을 요구한다. migration 검증은 같은 검사에 구/신규 DB의 보호 원천 count/hash와 모든 상태의 큐 count/hash 비교를 추가한다. 단일 run에서 하나라도 다르면 수렴 계약 구현은 미완료다.

WPF 앱은 로컬 `notifications` 테이블과 알림 창으로 문서, FieldComment, 작업순서 이벤트 알림을 확인하고 읽음 처리한다. 서버 URL과 로그인이 있으면 `채널함`, `채널 관리`, `인수인계 확인 현황` 화면에서 FastAPI 채널/인수인계 API를 직접 호출한다. 채널함은 내 채널, 사용자별 알림, 인수인계 목록을 조회하고 메시지 읽음, 내 receipt 상태 변경, 원천 링크 복사, 후속 FieldComment 생성을 수행한다. 후속 FieldComment는 인수인계 ID·작성자·정리한 내용을 hash한 안정 idempotency key를 사용한다. 코멘트 저장 뒤 채널 이벤트 응답이 유실되면 같은 코멘트를 다시 읽고 기존 채널 메시지를 확인한 뒤 누락된 메시지만 재시도하므로, 화면은 전체 실패가 아니라 코멘트 보존과 채널 알림 대기를 구분한다. 주 창이 열려 있는 동안 `server_notification_cursors`의 서버 scope·사용자별 마지막 성공 cursor 다음 알림을 기본 15초 간격으로 조회하고, `server_notification_messages`의 `message_id`로 멱등 처리한 뒤 같은 트랜잭션에서 cursor를 전진시킨다. 연결 실패 시 최대 120초까지 backoff하며 401이면 cursor를 유지한 채 중단한다. 저장 row가 없는 사용자는 cursor 0부터 최대 100건씩 빠르게 따라잡고 한글 진행 상태를 표시한다. 서버 cursor 역행은 자동 복구하지 않고 polling을 중지하며 Core 서비스가 `admin`, `system-admin` role을 다시 확인한 경우에만 현재 scope·사용자의 cursor 초기화를 허용한다. 초기화 뒤에도 기존 처리 `message_id`는 보존해 재조회 부작용을 막는다. 채널 관리는 채널 생성, 멤버 추가/제외를 제공한다. 인수인계 확인 현황은 활성 채널 정보를 함께 읽어 운영 단위·채널별 목록과 미확인·후속 조치 인원 합계를 표시하고, 수신자별 receipt 상태 변경과 후속 FieldComment 생성을 제공한다. 서버 로그인한 `admin`, `system-admin`은 `사용자 관리` 화면에서 서버 계정 생성, 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·폐기를 수행한다. 로컬 로그인은 별도 로컬 계정 화면을 사용한다. `admin`, `system-admin`은 `승인 단말` 화면에서 서버 단말 목록·상세·마지막 접속을 조회하고 등록, 정보/상태 변경, 교체를 수행한다.

Android 앱은 현장 단말 입력과 작업 중 문서 열람을 우선한다. 현장 작업자는 승인된 `deviceId`로 로그인하고 공개 문서 목록/상세 조회, PDF·이미지·TXT 앱 내부 보안 열람, FieldComment와 사진 기록, 신호등식 상태 기록을 수행한다. 인수인계 작성 화면에서는 현재 사용자의 활성 업무 채널과 수신자를 고르고 작업순서 항목, 공개 문서, 보관되지 않은 FieldComment 또는 작업내역을 원천으로 연결한다.

FieldComment, 사진, 신규 인수인계와 받은 인수인계의 확인·보류·후속 FieldComment는 Keystore AES-GCM으로 보호한 outbox에 먼저 저장한다. 받은 인수인계의 작성 중 후속 입력도 서버 URL+사용자+인수인계 범위의 암호문으로 보관하고 outbox 저장 뒤에만 비운다. 선택한 사진은 상태 문구와 축소 미리보기로 확인하며 저장이 끝나면 선택 상태와 미리보기를 비운다. 마지막으로 서버가 확인한 채널·수신자 목록은 서버 URL+사용자 scope별 암호문으로 보관하되, 서버는 실제 전송 때 멤버십과 원천 공개 상태를 다시 검사한다. 화면 상단은 전송 완료·대기·실패를 서로 다른 아이콘과 한글 상태명·건수로 구분하고, 단말 보존 상태, 다음 자동 전송 시점, 자동 재시도 한도와 승인 단말 ID를 계속 보여준다. 후속 FieldComment 저장 뒤 채널 알림만 실패한 항목은 부분 성공으로 표시하며 다음 시도에서 알림만 보낸다. 앱 화면과 로그인 세션의 foreground service는 기본 15초 간격으로 `PENDING`과 재시도 시점이 된 `FAILED` 항목을 자동 전송한다. 사용자가 누르는 `실패 항목 다시 보내기`는 로그인 상태의 `FAILED` 항목만 같은 멱등키로 즉시 다시 보내며 `PENDING`과 `SYNCED`는 선택하지 않는다.

본문은 사용자·세션·승인 단말·현재 공개 버전에 묶인 단기 1회 grant로 받아 앱 내부 난수 캐시에서만 표시하며 외부 열기·공유를 제공하지 않는다. foreground service는 채널 알림도 기본 15초 간격으로 polling하고 재부팅·네트워크 단절 뒤 서버 주소+사용자 scope별 마지막 cursor부터 재개한다. 표시한 공개 `message_id`는 별도 SQLite 원장에 `(server_user_scope, message_id)`로 기록해 cursor 재조회 때 같은 알림을 다시 표시하지 않는다. polling의 첫 401은 refresh token을 보존한 채 회전을 한 번 시도하고, 회전 뒤 재거부 또는 비활성 단말 403에서 세션을 폐기한다. 단순 연결 실패는 세션과 cursor를 유지한다. 인수인계는 같은 알림 스트림에서 받고 확인·보류와 후속 FieldComment를 남긴다. Android의 장기 기준 데이터는 FastAPI 서버에 남기며 로컬에는 암호화 outbox, 작성 중 후속 입력, 채널·수신자 선택 캐시, 처리한 알림 원장과 열람 중 즉시 정리할 캐시만 둔다. 로그인, 문서, 알림, 인수인계 API 실패는 서버 원문을 화면에 직접 표시하지 않고 연결 실패·시간 초과와 HTTP 상태를 현장 사용자가 조치할 수 있는 한글 안내로 바꾼다.

## 주요 도메인

### 변경 서비스 책임 경계

FastAPI 라우터는 인증 의존성, 공개 요청·응답 모델과 HTTP 오류 변환만 맡는다. FieldComment는 계약 DTO, 조회 조립, 검토 전이, 첨부 검증을 분리하고, 보고서는 source 가시성·version/revision/hash 고정 검증과 상태 전이를 별도 서비스에 둔다. 작업순서는 revision 선점, change history, 알림 후보와 receipt 기록을 mutation 서비스가 함께 처리한다. 상태를 바꾸는 서비스 진입점이 transaction의 commit/rollback을 소유하며 하위 검증·조회 함수는 commit하지 않는다. 업무 row·도메인 receipt·공통 receipt·감사는 같은 transaction에 포함하고, FieldComment 일괄 검토만 항목 하나를 원자 단위로 삼아 성공 항목을 보존한다.

WPF의 공개 `FieldCommentService`는 기존 호출 계약을 유지하는 facade다. SQLite 쓰기와 첨부 저장은 `FieldCommentRepository`, 검토 작업함 조회는 `FieldCommentWorkbenchQuery`, 허용 상태와 전이 검증은 `FieldCommentWorkflowService`가 맡는다. 의존 방향은 facade → query/repository/workflow이며 query와 repository가 서로 호출하지 않는다.

문서 동기화의 자동 수렴 경계는 활성 태그의 독립 추가·제거 집합까지다. 서버가 태그 기준 snapshot을 복원할 수 있고 양쪽 delta가 같은 태그에서 반대 방향이 아닐 때만 자동 병합한다. 파일/버전, 문서·버전 상태, 누적 구 공개 큐와 soft delete는 409 이후 `CONFLICT` 작업함으로 이동하며 서버값 read-back, 로컬 intent, 기준 snapshot hash, 원본 위치와 허용 행동을 보존한다. 현재 승인 작업함의 공개는 이 큐 경로와 분리한다. 앱 재시작·server epoch 변경·reconciliation은 큐와 해결 이력을 삭제하거나 자동 재기준화하지 않는다.

문서 공개 흐름은 `작성/새 version → 검토 요청 → 지정 검토자 승인 또는 반려 → 승인된 exact version 공개`다. 승인 projection과 append-only event가 문서 상태·공개 포인터와 분리되어 원본을 보존하며, 공개 mutation이 approval ID, document revision, version ID와 file hash를 transaction 안에서 다시 확인한다. 연결된 기존 `DOCUMENT` 채널에는 같은 transaction에서 문서 이벤트를 추가하고 기존 채널 멤버십·읽음 receipt·공통 감사를 그대로 사용한다. WPF 승인 작업함은 서버 상태를 권위로 다시 읽으며 로컬 선공개를 하지 않는다.

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
      -> DocumentMutationReceipt
      -> ControlledCopyGrant -> AuthSession + UserAccount + optional TerminalDevice
      -> DocumentTag
      -> DocumentTagRevision
      -> FieldComment
      -> DocumentViewLog

FieldComment
  -> FieldCommentAttachment
  -> Notification (WPF local)
  -> ReportSource

WorkSequenceBoard
  -> WorkSequenceItem
  -> WorkSequenceChangeHistory
  -> WorkSequenceMutationReceipt
  -> WorkSequenceNotificationCandidate
  -> Notification (WPF local)

Report
  -> ReportSource
  -> generated Document

AuditEventEnvelope
  -> SyncMutationReceipt
      -> DocumentMutationReceipt | FieldCommentReviewMutationReceipt
      -> ReportMutationReceipt | WorkSequenceMutationReceipt
  -> legacy ActivityHistory (read-only combined query, no backfill)

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

서버-WPF 동기화에서는 같은 문서의 서버 ID 선행 조건을 우선한다. 재시도 큐는 문서 등록, 문서 버전, 누적 구 공개 큐, 상태, 태그, FieldComment, FieldComment 검토, 첨부, 접근 로그, 보고서 순서로 처리한다. 보고서는 여러 문서의 근거를 묶어도 모든 비보고서 전송 대기 항목보다 뒤에 배치한다. 문서 최초 등록이 서버 ID를 받아야 문서 버전, 태그, FieldComment, 접근 로그가 후속 서버 ID에 연결된다. 현재 공개는 승인 작업함에서 직접 처리하며 `PUBLISHED` 진입은 공개 API만 수행한다. 구 공개·문서 상태·태그 큐에 생성 당시의 `base_server_revision`이 없으면 최신값을 추정해 보내지 않고 서버 호출 전에 `LEGACY_BASE_MISSING` 충돌로 보존한다.

## FieldComment

FieldComment는 문서 파일 개정이 아니라 현장 원천 기록이다. 새 WPF 코멘트는 `field_comments`에 저장되며 문서 버전을 증가시키지 않는다. 첨부 사진/파일은 `field_comment_attachments`에 별도로 저장된다.

관리자 검토 화면은 FieldComment 원천을 읽기 전용으로 표시하고 상태·기한 초과·담당자·라인/설비/공정/오류 태그·우선순위/상충·첨부·보고서 연결을 필터링하며 필터를 로컬 SQLite 저장 보기로 보존한다. 상세는 서버 원천 hash, 첨부 수, 관찰 문서 버전, 채널 권한과 상충 판단 근거를 표시한다. 상단 대시보드는 서버가 현재 `field_comments`와 `report_sources`에서 계산한 미검토·상충·안전/품질 위험·보고서 미연결·담당자 없음 수를 보여준다. WPF는 실제 현장 AI 준비도를 같은 화면에 표시하되 합성·시험 수치를 실제 현장 수치에 더하지 않는다. 다중 선택은 `/bulk-review/preview` 표에서 항목별 허용 전이와 실패를 확인한 뒤 `/bulk-review/execute`로 최대 200건을 처리한다. 서버는 항목별 transaction·revision·receipt를 반환해 일부 실패나 응답 유실에도 성공 결과를 보존하고 WPF는 성공 snapshot만 로컬에 반영한다. `red` 신호 또는 상충 원천의 결정 상태는 분석자와 다른 사용자가 바꿔야 한다.

## 작업순서

작업순서는 루트의 `작업순서` 폴더에 둘 수 있는 문서와 별개인 운영 보드이다. `work_sequence_boards`와 `work_sequence_items`가 현재 작업순서와 상태를 관리하고, 순서/상태 변경은 이력과 알림 후보를 만든다.

WPF 작업순서 관리자와 TV 화면은 FastAPI의 목록·상세 snapshot을 직접 읽는다. 관리 화면은 snapshot의 `board_revision`을 `baseBoardRevision`으로 보내고 사용자 동작마다 새 mutation key를 생성한다. 응답 유실 가능성이 있는 전송 오류는 같은 key로 한 번 재시도하며, 409 `WORK_SEQUENCE_STALE_REVISION`이면 한글 충돌 안내 후 서버 snapshot을 다시 읽어 사용자가 내용을 확인하고 재시도하게 한다.

서버-WPF 동기화 큐는 작업순서 보드/항목/이력을 대상으로 하지 않는다. 서버 URL·로그인·호환 응답이 없거나 조회가 실패하면 WPF 로컬 테이블과 화면에 남은 값은 `읽기 캐시/초안`으로만 표시하고 생성·항목 추가·순서·상태 확정 버튼을 차단한다. 기존 로컬 row와 테스트 기록은 보존한다. 서버는 mutation, revision 증가, 의미상 change history 1건과 mutation receipt를 한 transaction으로 commit하고, 순서·상태 변경에는 알림 후보도 함께 저장한다.

## 채널 알림과 인수인계

Windows와 Android의 알림은 장기적으로 개인 메신저가 아니라 업무 채널 모델로 다룬다. 채널은 라인, 설비, 공정, 작업조, 작업내역, 인수인계 같은 운영 단위에 연결된다. 사용자는 자신이 속한 채널의 문서 공개/변경, FieldComment 등록/검토 요청, 작업순서 변경, 인수인계 등록/확인 요청 알림을 받는다.

현재 구현된 알림은 WPF 로컬 `notifications`, `server_notification_cursors`, `server_notification_messages`, Android의 처리 알림 원장, 서버 작업순서 알림 후보(`work_sequence_notification_candidates`), FastAPI 공통 채널 모델(`notification_channels`, `notification_channel_members`, `channel_messages`)이다. WPF는 문서, FieldComment, 작업순서 이벤트 알림을 로컬 DB에 저장하고 읽음 처리하며, 서버 채널 화면에서는 내 채널/메시지/인수인계를 조회하고 읽음/수신 확인을 남긴다. Windows와 Android는 전경에서 `/api/v1/notifications?afterId={cursor}`를 polling하고 응답 처리가 끝난 뒤에만 cursor를 전진시킨다. Android는 사용자별 cursor를 `SharedPreferences`에, 처리한 `message_id`를 사용자 scope별 SQLite 원장에 보존한다. 현재 사용자 receipt의 확인·보류와 같은 원천의 후속 FieldComment는 암호화 outbox에서 재시도한다. 활성 채널·수신자와 업무 원천을 골라 작성한 신규 인수인계도 같은 outbox에서 같은 멱등키로 다시 보낸다. WPF는 서버 scope·사용자별 cursor와 처리한 `message_id`를 SQLite에 영구 보존한다. FastAPI는 채널 멤버십, 채널 메시지, cursor 기반 사용자별 알림 증분 조회/읽음 처리, 인수인계 생성과 수신 확인 API를 제공한다.

채널 메시지는 자유 대화를 무제한 보관하는 기능이 아니다. 각 메시지는 가능한 한 `document_id`, `field_comment_id`, `work_record_id`, `work_sequence_item_id`, `handover_id` 같은 원천 ID를 가져야 하며, 이후 보고서와 AI 검색 후보가 원문 근거로 역추적할 수 있어야 한다. 인수인계는 채널에 등록되는 업무 이벤트이며, 수신자는 확인, 보류, 후속 FieldComment 작성 같은 상태를 남길 수 있다.

초기 구현에서는 개인 DM, 사내 메신저 대체, 개인 휴대폰 알림 수집, GPS/근태 추적을 포함하지 않는다. 채널/인수인계 API는 서버 로그인 사용자, role, 채널 멤버십 기준으로 접근을 제한한다. Android는 `terminal_devices` 승인 상태를 로그인 단계에서 검증하고, Windows는 관리자/감독 화면 중심으로 같은 서버 채널 데이터를 공유한다.

## 보고서

보고서는 FieldComment 작업함·상세에서 `SELECTED` 원천을 넘기고, 공개 문서와 작업순서 항목/이력을 더해 수동 초안을 만드는 흐름으로 연결된다. WPF 초안 화면은 `FIELD_COMMENT`, `DOCUMENT`, `WORK_SEQUENCE_HISTORY` 후보 가운데 서로 다른 source type을 2종 이상 선택하게 하고 기존 보고서의 고정 source도 유형별로 보여준다. Core의 초안 고정은 `WORK_SEQUENCE_ITEM`도 지원하며 작업순서 항목은 서버의 현재 항목과 최신 변경 기록을, 작업순서 이력은 선택한 변경 기록의 존재와 ID를 확인한다. 검증할 수 없는 원천 유형이나 달라진 snapshot이 하나라도 있으면 서버 초안을 만들지 않는다.

서버 보고서는 `DRAFT → REVIEWED → APPROVED → ARCHIVED`로 전이한다. WPF는 검토중 전이를 거쳐 확정 저장하며 확정 단계에서만 문서를 생성한다. 생성 문서 상태는 요청의 `documentStatus`로 연결하므로 보고서 확정이 자동 공개 최신본을 뜻하지 않는다. 검토중 전환 뒤 편집 내용이 달라지면 새 초안과 재검토를 요구하고, 보고서를 보관하면 연결된 생성 문서와 버전도 함께 보관하되 고정 source와 receipt는 유지한다. 최종 저장은 로컬 보고서 문서와 source를 먼저 보존한 뒤 `/api/v1/reports`를 호출한다. 전송 실패나 source 변경 충돌은 `server_sync_queue`에 남고 성공하면 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`를 채운다. 서버는 FieldComment의 관찰 버전과 선정 `review_revision`, 원천 hash를 `report_sources`에 고정하고 상태 전이·문서 저장 직전에 상태·version·revision·hash·채널 권한을 다시 검사한다. 확정 뒤 원천이 바뀌어도 보고서 상세는 당시 source snapshot을 유지하며 현재 채널 권한을 통과한 사용자가 type/ID/version/revision/trace/hash로 역추적할 수 있다. AI가 자동 작성하는 보고서는 아직 구현 범위가 아니다.

## 후속 연동

MES/ERP는 후속 연동 대상이다. 현재 코드는 내부 작업순서와 문서/FieldComment 기록을 먼저 안정적으로 축적하는 단계다.

후속 어댑터가 도입되더라도 초기 수동 입력 데이터와 같은 연결점을 사용한다. 외부 작업지시는 `work_records.work_order_no`, `work_records.external_system`, `work_records.external_ref_id`, `work_sequence_items.work_order_no`로 연결하고, 작업지시 문서는 `work_records.work_instruction_document_id`와 `work_sequence_items.document_id`로 연결한다. FieldComment와 보고서는 `work_record_id`와 `report_sources`를 통해 작업내역과 근거를 추적한다.

AI 관련 기초 구현은 외부 호출 경계와 분리된 `ai_search_candidates` read model이다. 서버 DB에서 근거 후보를 재생성하고 목록과 품질을 점검한다. 공개 문서 후보는 삭제되지 않은 공개 문서 버전만 사용하고, 보고서 source도 실제 원천을 다시 확인한다. 특히 `DOCUMENT` 원천이 삭제 상태이거나 `deleted_at`이 설정되어 있으면 보고서가 남아 있어도 검색 후보로 만들지 않는다. WPF `AI 근거 후보 운영 점검` 화면은 서버 후보 재생성, source별 후보 수, 제외 사유와 운영 조치, FieldComment 검토 준비도, 후보 목록, 원천 추적값 복사를 제공한다. 운영 점검 흐름은 후보 재생성, source별 후보 수 확인, 제외 사유와 운영 조치 확인, 후보 row에서 원천 문서 버전/FieldComment/작업순서 이력/보고서 source로 역추적하는 순서다. FieldComment 검토 준비도는 분석/검토/선정 상태 100건 기준의 부족분을 먼저 보여주며, 이 수치가 부족하면 AI 답변 생성보다 FieldComment 검토와 보고서 source 정리를 우선한다.

외부 provider 착수 전 회귀 흐름은 WPF에서 후보 포함 근거·수동 제외 원천으로 질문 사례 구성 → 첫 승인 → 다른 사용자의 2차 승인 → 승인 사례를 dataset version으로 구성 → 작성자와 다른 검토자 → 제한 role의 독립 2단계 승인 → 승인 dataset에 결합한 동일 snapshot 평가 2회 → 권한을 반영한 후보 순위와 기대 candidate/source/version/trace ID 비교 → 원천 URI 확인 → 재생성 전후 ID/content hash와 순위 비교 → 서버가 snapshot hash로 고정한 24칸 표본을 WPF에서 두 사람이 독립 검토 → 불일치 시 같은 화면에서 제3 합의 순서다. WPF `24칸 독립 검토`는 첫 판정의 blind 상태, 두 판정 비교, 불일치 case 축소, 기대·실제·제외 근거 trace를 서버 상태에 따라 표시한다. 실행과 케이스 snapshot은 서버 SQLite에 누적하며 삭제·비공개·보관/제외·민감정보·고객 식별자·로컬 경로·사라진 보고서 원천·권한 없는 채널은 부정 근거로 기록한다. 합성/시험 스모크, `PILOT`, 고객 승인 `ANONYMOUS_FIELD`는 별도 지표이며 provider 착수 48건에는 마지막 분류만 사용한다. 근거가 없는 질문은 답변 생성 대상이 아니라 `INSUFFICIENT_EVIDENCE`로 고정한다. dataset 조회·변경·전이와 대체본 참조는 서버 고객·현장·DB scope를 다시 검사하고 대체본은 라인·준비도 계열·dataset key도 같아야 한다.

외부 AI 1단계는 위 read model과 분리된 후속 쓰기 흐름이다. 현재 구현은 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`를 기본값으로 두고, 보고서 작성 role, 허용 목적, 고객·현장·provider·model 승인, 승인 프롬프트, 원천 상태, 작성자 role, 채널 멤버십, 승인 source type, 민감정보 정책과 응답 인용 ID를 검사한다. 고객·현장별 민감정보 정책은 불변 버전으로 작성한 뒤 서로 다른 `system-admin`이 검토하고 승인하며, 활성·대체·승인 철회·폐기 이력을 남긴다. provider 호출 직전과 응답 직후에는 활성 정책의 ID·content hash·revision snapshot을 다시 비교한다. provider 중립 adapter 뒤에서 JSON 구조·크기·중복·prompt injection과 claim/summary의 규칙 기반 의미 일치를 검사하고, 호출 전후 원천·권한·승인·민감정보 정책이 달라지면 결과를 폐기한다. 적격·제외 후보를 원문 없이 질의 시점 snapshot으로 남기고, 근거 없음·상충·최신성 불명·낮은 확신은 정상 `INSUFFICIENT_EVIDENCE`로 종료한다. 결과는 작업순서·문서 상태·보고서 승인·설비를 변경하지 않는다.

외부 AI 운영 제어면은 `system-admin` 전용 `/api/v1/ai-operations`와 WPF `AI 운영` 화면으로 연결된다. 전송 승인은 고객·현장·provider·model·목적·source type과 만료 시각을 고정하고 생성·철회를 감사한다. 프롬프트는 새 불변 버전을 만든 뒤 `DRAFT → REVIEWED → APPROVED → ACTIVE → RETIRED` 순서로 관리하며 목적별 새 버전을 활성화하면 이전 활성 버전을 폐기한다. 전역/현장 정책은 kill switch, 일일 요청·동시성·timeout·비용 한도, 질의·응답·감사 보존 기간과 감사 CSV 허용 여부를 관리한다. 질의 감사·보존 이력·수동 보존 조작은 설정된 고객·현장 scope로 고정한다. 서버 lifespan 스케줄러와 `system-admin` 일괄·단일 실행 API는 질의 payload를 비식별화하고 응답 원문을 삭제하면서 hash와 참조·처리 감사를 보존한다. `ai_query_legal_holds`의 활성 보존 명령은 세 만료 경로보다 우선하며 해제 뒤에만 만료할 수 있다. WPF 화면은 질의 상세와 전체 hold·감사 이력을 조회하고 일괄·단일 만료 및 hold 설정·해제를 제공한다. 단일 조작은 이중 확인, 최신 `stateTag`, 안정 operation key와 완료 후 서버 read-back을 사용한다. provider 자격증명은 환경/비밀 저장소에만 두며 API와 화면은 설정 여부만 노출한다.

provider 경계는 정제 질의, 최소 발췌, candidate/source/version/trace ID, content hash, 순위, prompt version과 허용 출력 형식만 받는다. fake/recording adapter가 기본 검증 경로이고 generic JSON 네트워크 adapter는 명시적 `test` scope에서만 생성된다. 권한 없거나 상태가 바뀐 원천, 전송 금지 정보는 경계 DTO에 포함되지 않는다. 데이터 모델은 [데이터 모델](./data-model.md#외부-ai-질의와-호출-로그-안전장치)와 [외부 AI 운영·보존 모델](./data-model.md#외부-ai-운영보존-모델), API 계약과 테스트 기준은 [API 문서](./api.md#외부-ai-근거-검색과-요약-안전장치)와 [외부 AI 운영 API](./api.md#외부-ai-운영-api), 전송 승인은 [보안 문서](./security.md#외부-ai-전송과-운영자-승인)를 따른다. 착수 기준은 [MVP 범위 문서](./mvp-scope.md#후속-계층-착수-기준)를 따른다.

## 서버 복구 경계 흐름

WPF는 문서 전송과 채널 polling보다 먼저 sync manifest를 조회한다. 명시적 복구 장애가 있거나 정규화 URL의 승인된 instance/epoch와 다르거나 서버 cursor가 역행하면 binding을 `RECONCILIATION_REQUIRED`로 바꾸고 두 흐름을 함께 중지한다. `이력 > 서버 재결합`은 서버 응답 확인과 안전 수렴 상태를 분리해 표시하고, 차단 원인, 보존 원천, 승인 전 금지 행동, 담당자, pilot run·backup set·복구 승인 ID, 다음 단계를 한 흐름에 둔다. 관리자가 inventory 판정을 생성해 `REBOUND/REQUEUE/CONFLICT` 전 항목을 감사·승인하면 mapping을 갱신하고 기존 처리 message_id를 유지한 채 cursor를 0으로 준비한다. 명시적 장애 표지가 있으면 binding은 `POST_APPROVAL_RESTART_REQUIRED`로 자동 전송·polling을 계속 막는다. 서버 정상 종료 → `FLOWNOTE_RESTORE_*` 표지 제거 → 서버 재시작 뒤 `업무 재개 확인`이 정상 manifest를 read-back해야 `POST_APPROVAL_VERIFICATION_REQUIRED`로 바꾸고 재추적·재전송·polling을 함께 시작한다. 연결 재개만으로 안전 수렴을 확정하지 않는다. DB·파일 책임 교차 검사, 비종결 큐, 중복 mutation, 권한 우회와 polling 추적 증거가 모두 통과한 뒤에만 실기 결과를 안전 수렴으로 승인한다.
