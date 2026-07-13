# FlowNote API

FastAPI 서버는 `/api/v1` 아래 REST API를 제공한다. 루트 `/`는 서비스 이름과 환경을 반환한다. `/`, `/api/v1/health`, `/api/v1/health/db`, `GET /api/v1/tags`를 제외한 현재 API는 Bearer token 기반 인증을 요구한다.

## 인증

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 사용자명/비밀번호 로그인, access token과 refresh token 발급. Android는 승인 단말 `deviceId`를 함께 전송 |
| POST | `/api/v1/auth/refresh` | refresh token 검증 후 같은 세션의 access/refresh token 회전 |
| POST | `/api/v1/auth/logout` | 현재 access token 세션을 `REVOKED`로 변경 |
| GET | `/api/v1/auth/me` | 현재 Bearer token 사용자 정보 조회 |

보호 API는 `Authorization: Bearer {access_token}`을 요구한다. access token은 HMAC 서명 payload이며 서버의 `auth_sessions` 상태와 `access_token_id`까지 검증한다.

서버 계정 발급, 잠금, 비밀번호 재설정, role 변경을 수행하는 공개 API는 현재 범위에 추가하지 않는다. 운영 배포 전 기준은 서버 PC의 `app.ops.server_accounts` 운영 스크립트이며, WPF 사용자 관리 화면은 로컬 SQLite 계정만 관리한다. 이 화면은 제목, 목록, 상세 안내에서 로컬 계정 전용임을 표시해야 한다. 운영 스크립트의 비밀번호 입력은 대화식이며 현재 최소 8자를 요구한다. 첫 로그인 후 비밀번호 변경 강제도 현재 응답 payload, 서버 컬럼, WPF 화면에 추가하지 않고 “운영 첫 로그인 전 비밀번호 변경” 절차로 통제한다. `must_change_password` 컬럼, 비밀번호 변경 API, WPF 강제 변경 화면은 후속 범위다.

운영 기준:

- 서버 로그인은 서버 `user_accounts`의 `is_active`와 `status = ACTIVE`를 모두 만족해야 한다.
- Android 현장 단말 로그인은 `deviceId`가 `terminal_devices.device_id`에 존재하고 `status = ACTIVE`여야 한다. 승인되지 않았거나 비활성 단말이면 403을 반환한다.
- 서버 로그인 성공 시 WPF는 서버 응답의 사용자 ID, 표시 이름, role을 현재 세션 기준으로 사용한다.
- 서버가 로그인 요청에 401 또는 403을 반환하면 WPF는 로컬 계정 로그인으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 WPF 로컬 계정 로그인을 사용한다.
- 서버 계정 운영 스크립트의 `create`, `reset-password`, `set-status`, `set-role` 경로는 `services/api/tests/test_server_account_ops.py`로 검증한다.
- refresh는 같은 `auth_sessions` row에서 access token ID와 refresh token hash를 회전한다. 이전 access token과 이전 refresh token은 거부된다.
- Android가 `deviceId`로 로그인한 세션은 `auth_sessions.device_id`에 승인 단말 ID를 보존한다. refresh는 같은 세션의 단말 ID를 유지한다.
- logout은 현재 세션을 `REVOKED`로 바꾸며 이후 같은 access token은 거부된다.
- WPF 서버 동기화 중 인증 만료, 토큰 교체, logout 폐기가 확인되면 `로그인이 만료되었거나 서버 인증이 해제되었습니다. 다시 로그인하세요. 로컬 데이터는 삭제되지 않습니다.` 문구를 표시하고 로컬 데이터와 동기화 큐를 삭제하지 않는다.

## 승인 단말 관리

아래 API는 `admin`, `system-admin`만 사용할 수 있다. 단말 상태는 `ACTIVE`, `INACTIVE`, `RETIRED`이며 `RETIRED` 단말은 다시 활성화할 수 없다. 단말 용도 `device_mode`는 현장 열람용 `viewer`와 관리 지원용 `admin_support`를 사용한다.

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/terminal-devices` | 승인 단말 목록. 선택적으로 `status` 필터 사용 |
| POST | `/api/v1/terminal-devices` | 승인 단말 등록 |
| GET | `/api/v1/terminal-devices/{device_id}` | 승인 단말 상세 조회 |
| GET | `/api/v1/terminal-devices/{device_id}/last-seen` | 상태와 마지막 로그인 성공 시각 조회 |
| PATCH | `/api/v1/terminal-devices/{device_id}` | 단말명, 용도, 위치, 그룹 변경 |
| PATCH | `/api/v1/terminal-devices/{device_id}/status` | 단말 활성·비활성·폐기 상태 변경 |
| POST | `/api/v1/terminal-devices/{device_id}/replace` | 기존 단말을 `RETIRED`로 바꾸고 교체 단말 등록 |

등록·정보 변경·상태 변경·교체는 `registered_by`, `updated_by`를 현재 서버 사용자 ID로 기록한다. 운영 변경은 `activity_history`에 `terminal_device.*` 이벤트, 변경 전후 JSON, 변경 사유로 남긴다. Android 로그인은 오직 `ACTIVE` 단말만 허용하고 성공할 때마다 `terminal_devices.last_seen_at`을 갱신하며 새 `auth_sessions.device_id`를 기록한다. 단말을 `INACTIVE` 또는 `RETIRED`로 바꾸거나 교체하면 해당 device ID의 기존 활성 세션도 같은 트랜잭션에서 `REVOKED`로 폐기한다.

## Health

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/health` | API 상태 확인 |
| GET | `/api/v1/health/db` | DB 연결 확인 |

## 문서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/documents` | multipart 문서와 최초 버전 등록 |
| GET | `/api/v1/documents` | 전체 문서 목록 |
| GET | `/api/v1/documents/published` | 공개 문서 목록 |
| GET | `/api/v1/documents/{document_id}` | 문서 상세 |
| GET | `/api/v1/documents/{document_id}/published` | 공개 버전 조회 |
| PUT | `/api/v1/documents/{document_id}/tags` | 문서 태그 교체 |
| PATCH | `/api/v1/documents/{document_id}/status` | 문서 상태 변경 |
| GET | `/api/v1/documents/{document_id}/versions` | 문서 버전 목록 |
| POST | `/api/v1/documents/{document_id}/versions` | 새 파일 버전 등록 |
| PATCH | `/api/v1/documents/{document_id}/versions/{version_id}/status` | 버전 상태 변경 |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/publish` | 특정 버전을 공개 버전으로 지정 |

문서 생성 시 허용되는 상태는 `WORKING`, `IN_REVIEW`, `ARCHIVED`이다. `PUBLISHED`는 publish 엔드포인트로만 만든다.

## 접근 로그

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/documents/{document_id}/access-logs` | 문서 접근 로그 등록 |
| GET | `/api/v1/documents/{document_id}/access-logs` | 문서 접근 로그 조회 |

`action` 값은 `view_started`, `view_closed`, `download_blocked`, `auto_closed`를 사용한다. 조회는 `admin`, `system-admin`만 가능하다.

## FieldComment

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/field-comments` | FieldComment 원천 기록 등록 |
| GET | `/api/v1/field-comments` | FieldComment 목록 조회 |
| GET | `/api/v1/field-comments/{comment_id}` | FieldComment 상세 조회 |
| PATCH | `/api/v1/field-comments/{comment_id}` | 상태, 정리 내용, 분석 내용 갱신 |
| POST | `/api/v1/field-comments/{comment_id}/attachments` | 첨부 파일 등록 |
| GET | `/api/v1/field-comments/{comment_id}/attachments` | 첨부 파일 목록 조회 |
| GET | `/api/v1/documents/{document_id}/field-comments` | 특정 문서의 FieldComment 조회 |

FieldComment는 `documentId`, `structureItemId`, `workRecordId` 중 하나 이상을 참조해야 한다. 현재 구조에서는 문서 참조가 주 사용 경로다.

`GET /api/v1/field-comments`는 관리자 검토 화면 기준으로 `status`, `documentId`, `documentText`, `author`, `tag`, `createdFrom`, `createdTo`, `limit` 필터를 지원한다. WPF 관리자 화면은 같은 기준으로 로컬 `field_comments`, 문서, 문서 태그, 첨부 개수를 함께 조회한다.

WPF 관리자 검토 화면은 선택한 FieldComment의 `normalized_content`, `analysis_content`, `status`를 수정하고 `server_sync_queue`에 `entity_type = field_comment_review`, `action = update_field_comment_review`로 서버 PATCH 재시도 항목을 남긴다. 서버 ID가 아직 없는 로컬 FieldComment는 선행 등록 동기화가 끝난 뒤 검토 변경 PATCH를 재시도한다.

## 태그

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/tags` | 태그 목록 조회 |
| POST | `/api/v1/tags` | 태그 생성 |

태그 타입은 `equipment`, `item`, `process`, `error_type`, `line`, `location`, `custom`을 허용한다.

## 작업순서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/work-sequence-boards` | 작업순서 보드 생성 |
| GET | `/api/v1/work-sequence-boards` | 작업순서 보드 목록 |
| GET | `/api/v1/work-sequence-boards/{board_id}` | 작업순서 보드 상세 |
| POST | `/api/v1/work-sequence-boards/{board_id}/items` | 항목 추가 |
| PUT | `/api/v1/work-sequence-boards/{board_id}/items/order` | 항목 전체 순서 변경 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/items/{item_id}/status` | 항목 상태 변경 |
| GET | `/api/v1/work-sequence-boards/{board_id}/history` | 변경 이력 조회 |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | 알림 후보 조회 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | 알림 후보 상태 변경 |

## 채널 알림과 인수인계

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/notification-channels` | 업무 채널 생성. 생성자는 `OWNER` 멤버로 자동 등록 |
| GET | `/api/v1/notification-channels` | 현재 사용자가 속한 채널 목록. `admin`, `system-admin`은 전체 조회 |
| GET | `/api/v1/notification-channels/{channel_id}` | 채널 상세 조회 |
| POST | `/api/v1/notification-channels/{channel_id}/members` | 채널 멤버 추가 또는 재활성화 |
| GET | `/api/v1/notification-channels/{channel_id}/members` | 채널 멤버 목록 |
| PATCH | `/api/v1/notification-channels/{channel_id}/members/{member_id}` | 멤버 역할 또는 상태 변경 |
| POST | `/api/v1/notification-channels/{channel_id}/messages` | 채널 메시지 등록 |
| GET | `/api/v1/notification-channels/{channel_id}/messages` | 채널 메시지 조회 |
| GET | `/api/v1/notifications` | 현재 사용자 기준 채널 알림 목록. `afterId`, `limit`, `unreadOnly` 지원 |
| PATCH | `/api/v1/notifications/{message_id}/read` | 현재 사용자의 해당 채널 메시지 읽음 처리 |
| POST | `/api/v1/handovers` | 인수인계 등록, 수신자별 receipt 생성, 채널 메시지 생성 |
| GET | `/api/v1/handovers` | 현재 사용자가 속한 채널의 인수인계 목록 |
| GET | `/api/v1/handovers/{handover_id}` | 인수인계 상세와 수신자별 receipt 조회 |
| PATCH | `/api/v1/handovers/{handover_id}/receipts/{receipt_id}` | 수신자별 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 상태 기록 |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | 작업순서 변경으로 생성된 알림 후보 조회 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | 작업순서 알림 후보 상태를 `CANDIDATE`, `SENT`, `DISMISSED` 중 하나로 변경 |

채널 유형은 `LINE`, `EQUIPMENT`, `PROCESS`, `WORK_GROUP`, `HANDOVER`, `WORK_RECORD`, `CUSTOM`이다. 채널 메시지 유형은 `NOTICE`, `DOCUMENT_EVENT`, `FIELD_COMMENT_EVENT`, `WORK_SEQUENCE_EVENT`, `HANDOVER`, `SYSTEM`이다. 인수인계 상태는 `DRAFT`, `SENT`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`, `ARCHIVED`이고, 수신 상태는 `UNREAD`, `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`이다.

채널 메시지와 인수인계는 `sourceType`, `sourceId`, `sourceVersionId`로 원천을 추적한다. 메시지 source는 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `REPORT`, `HANDOVER`, `SYSTEM`을 허용한다. 인수인계 source는 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `REPORT`, `CHANNEL_MESSAGE`를 허용한다.

알림 증분 조회 계약은 다음과 같다.

- `afterId`는 마지막으로 처리 완료한 응답 항목의 정수 `cursor`다. 생략하면 최신순 목록, 지정하면 `cursor > afterId`인 항목을 cursor 오름차순으로 반환한다.
- `limit`은 1~500이고 기본값은 100이다. `unreadOnly` 기본값은 `false`이며 필터 적용 후 limit을 계산한다.
- 응답의 `cursor`는 서버 `channel_messages`의 단조 증가 식별자이고 `message_id`는 사용자 표시와 읽음 처리의 공개 멱등 키다. 생성 시각은 cursor 경계로 사용하지 않는다.
- 응답을 모두 로컬 처리한 뒤 마지막 cursor를 저장한다. 응답 도중 실패하면 기존 cursor로 다시 조회하고 `message_id`로 이미 표시한 항목을 제거한다.
- 인수인계 등록은 `message_type = HANDOVER`, `source_id = handover_id`인 채널 메시지를 함께 만들므로 같은 알림 증분 스트림으로 전달된다. receipt 갱신은 동일 상태와 note를 반복 요청해도 추가 상태 변경 이력을 만들지 않는다.
- 멤버십이 `ACTIVE`인 현재 사용자 채널만 반환한다. 권한 없는 채널 및 다른 사용자의 알림은 cursor 범위에 있어도 반환하지 않는다.

채널 생성과 메시지 등록은 서버 인증이 필요하다. 채널 생성은 문서/작업순서 쓰기 role 기준을 사용하며, 채널 조회, 메시지 조회, 인수인계 조회는 채널 멤버 또는 `admin`, `system-admin`만 가능하다. 수신확인은 해당 receipt 수신자 또는 `admin`, `system-admin`만 변경할 수 있다. 개인 DM, 개인 메신저 수집, GPS, 근태 기능은 이 API에 포함하지 않는다.

## 보고서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/reports/drafts` | 수동 보고서 초안 생성 |
| POST | `/api/v1/reports` | 보고서 저장, 선택 시 문서로 저장. `idempotencyKey`를 보내면 같은 키의 재시도는 기존 보고서를 반환 |
| GET | `/api/v1/reports` | 보고서 목록 |
| GET | `/api/v1/reports/{report_id}` | 보고서 상세 |

보고서 source 타입은 `FIELD_COMMENT`, `DOCUMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `WORK_RECORD_VERSION`을 사용한다. WPF 보고서 초안의 FieldComment 후보는 `SELECTED`, `REVIEWED`, `ANALYZED` 순으로 우선 노출하고 `EXCLUDED`, `ARCHIVED` 상태는 후보에서 제외한다.

## AI 검색 근거 후보

AI 검색 후보 API는 자동 조언이 아닌 “근거가 있는 검색과 요약”의 read model 관리 범위다. 이 API는 외부 AI 기능 플래그와 독립적으로 재생성·조회·품질 점검을 계속한다. 실제 외부 provider 네트워크 호출, 자동 작업지시 변경, 자동 의사결정은 포함하지 않는다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/ai-search/candidates/rebuild` | 현재 DB 기준으로 검색 후보를 재생성하고 후보 수와 제외 사유를 반환 |
| GET | `/api/v1/ai-search/candidates` | 검색 후보 목록 조회. `sourceType`, `sourceId`, `limit`으로 제한 가능 |
| GET | `/api/v1/ai-search/quality` | 후보 수, 원천별 개수, 제외 사유, FieldComment 검토 상태 부족분 조회 |
| POST | `/api/v1/ai-search/evaluations` | 외부 AI 호출 없이 질문별 기대 근거와 실제 후보를 비교하고 재현성 snapshot을 누적 저장 |

검색 후보 원천은 `PUBLISHED_DOCUMENT_VERSION`, `FIELD_COMMENT`, `WORK_SEQUENCE_HISTORY`, `REPORT_SOURCE` 네 종류만 허용한다. 각 후보 응답은 안정된 `candidate_id`, `content_hash`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `parent_type`, `parent_id`를 포함해 원문 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 근거 row로 역추적할 수 있어야 한다. `candidate_id`는 source type/id/version 조합의 결정적 hash이며 원천 내용이 바뀌지 않으면 재생성 뒤에도 유지되고, 검색 본문 변경은 `content_hash`로 구분한다.

평가 요청은 `runLabel`, 선택적 `evaluateAsUserId`, `cases[]`를 받는다. 각 case에는 `caseKey`, `question`, `expectedOutcome`, `expectedEvidence[]`, `expectedExcluded[]`, `limit`을 둔다. 서버는 후보를 두 번 재생성해 ID·content hash와 순위를 비교하고, 기대/실제 candidate·source·version·trace ID, 내부 원천 URI, 제외 사유, 순위 hash를 `ai_search_evaluation_runs`와 `ai_search_evaluation_cases`에 저장한다. 질문과 일치하는 적격 후보가 없으면 답변을 만들지 않고 `INSUFFICIENT_EVIDENCE`로 판정한다. 채널에 연결된 원천은 평가 사용자에게 활성 멤버십이 없으면 `CHANNEL_ACCESS_DENIED`로 제외한다. 이 API는 provider client를 호출하지 않는다.

`GET /api/v1/ai-search/quality`의 `latest_evaluation`은 최근 실행의 통과 건수, 네 원천 커버, ID/hash·순위 안정성, 주요 제외 사유, FieldComment 검토 부족분과 `provider_start_ready`를 반환한다. 착수 가능은 모든 평가 통과, 네 원천 커버, 재현성 통과, 검토 완료 FieldComment 100건 충족을 모두 요구하며 외부 전송 승인이나 기능 플래그를 자동으로 켜지는 않는다.

WPF `AI 근거 후보 운영 점검` 화면은 `POST /api/v1/ai-search/candidates/rebuild`로 후보를 재생성한 뒤 `GET /api/v1/ai-search/quality`의 `counts_by_source_type`, `excluded_counts_by_reason`, `excluded_reason_guidance`, `field_comment_review_readiness`를 표시한다. 원천별 후보 수는 네 source 타입을 항상 표시하고, FieldComment 검토 준비도는 `ANALYZED`, `REVIEWED`, `SELECTED` 상태 합계가 100건에 부족한 수를 보여준다. 후보 목록에서 운영자는 `trace_table`, `trace_id`, `trace_version_id`로 원문 문서 버전, FieldComment, 작업순서 이력, 보고서 source row로 이동해 근거를 확인하며 선택 후보의 추적값을 클립보드에 복사할 수 있다.

후보 재생성의 제외 사유는 공개되지 않은 문서 버전, 제외/보관 FieldComment, MES 통합 입력 FieldComment, 내용 없는 FieldComment, 역추적 텍스트 없는 작업순서 이력, 누락/보관 보고서 source, 원천이 사라진 보고서 source를 구분해 반환한다. 보고서 source가 `DOCUMENT`를 가리키면 해당 문서와 선택한 버전의 존재 여부를 확인하며, 문서가 `status = DELETED`이거나 `deleted_at`이 설정된 경우도 `report_source_missing_origin`으로 분류해 후보에서 제외한다. 각 제외 사유에는 운영자가 문서 공개, FieldComment 검토/분석, 보고서 source 정리 중 무엇을 해야 하는지 판단할 수 있는 `label`, `operator_action`, `source_type` 안내를 포함한다. `EXCLUDED`, `ARCHIVED` FieldComment는 AI 검색 후보와 보고서 초안 후보 양쪽에서 제외한다.

## 외부 AI 근거 검색과 요약 안전장치 골격

이 절의 질의 생성·조회 라우터와 차단/감사 골격은 구현되었다. 운영 provider client와 네트워크 호출, 재생성 라우터는 아직 구현하지 않는다. 외부 호출은 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=true`와 고객·현장별 운영자 승인이 모두 유효할 때만 `admin`, `system-admin`에게 허용한다. 허용 목적은 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`뿐이며 자동 의사결정, 작업지시 생성·변경, 승인·공개 자동화, 설비 제어, 안전·품질 판정 요청은 provider 호출 전에 `422 AI_SCOPE_NOT_ALLOWED`로 거부한다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/ai/queries` | 근거 검색·요약 질의 생성. 외부 호출이 꺼져 있으면 `503 AI_EXTERNAL_CALL_DISABLED`, 전송 승인이 없으면 `403 AI_TRANSFER_NOT_APPROVED` |
| GET | `/api/v1/ai/queries/{query_id}` | `admin`, `system-admin`이 질의 상태, 응답 저장 여부/hash, 차단 코드, 적격 근거 snapshot 조회. 현재는 호출자 본인 제한이나 응답 본문·citation 목록 반환은 없음 |
| POST | `/api/v1/ai/queries/{query_id}/regenerations` | 후속 계약. 보존 기간 안의 질의·프롬프트·근거 snapshot으로 재생성하며 현재는 미구현 |

`POST /api/v1/ai/queries` 요청:

```json
{
  "purpose": "EVIDENCE_SUMMARY",
  "query": "프레스 A 금형 교환 중 반복된 문제를 근거와 함께 요약해 주세요.",
  "candidateIds": ["candidate-..."],
  "responseStorageMode": "DO_NOT_STORE"
}
```

`candidateIds`는 선택 사항이며 생략하면 `ai_search_candidates` 정렬 순서의 최대 100건을 검사한다. 현재 서버는 후보의 source type이 전송 승인 범위인지 확인하고, 공개 문서·`ANALYZED`/`REVIEWED`/`SELECTED` FieldComment·존재하는 작업순서 이력·비보관 보고서 source만 적격 snapshot으로 저장한다. 부적격 후보는 snapshot row로 남기지 않는다. 현재 구현에는 원천별 호출 사용자의 열람 권한과 민감정보/외부 전송 금지 패턴 검사가 아직 없으므로 이 검사가 추가되기 전에는 운영 호출을 켜면 안 된다.

클라이언트는 provider, model, 시스템 프롬프트를 지정할 수 없다. 서버는 설정의 provider/model과 해당 목적에 대해 최근 승인된 미폐기 `ai_prompt_versions`를 선택한다. 현재 주입형 provider 경계로 넘기는 payload는 `purpose`, `queryHash`, `promptVersionId`, `candidateIds`뿐이며, 질의·프롬프트·근거 본문을 넘기지 않는다. 따라서 이 경계는 mock 검증용이고 실제 요약을 수행하는 provider client가 아니다.

성공 응답의 `grounded`는 `true`이고, `claims`의 모든 사실 주장에는 하나 이상의 `citations`가 있어야 한다. 현재 코드는 claim별 인용 ID를 snapshot과 대조하지만, 최상위 `summary`와 claim 텍스트의 의미적 일치를 따로 검증하지 않는다. 운영 provider 연동 전에 summary가 검증된 claim 밖의 사실을 추가하지 못하게 하는 계약과 테스트를 보강해야 한다. 각 citation은 `candidateId`, `sourceType`, `sourceId`, `sourceVersionId`, `traceTable`, `traceId`, `traceVersionId`, `internalSourceUri`를 포함한다. 문서 인용은 `document_id + version_id`, FieldComment 인용은 `comment_id`와 연결된 `document_version_id`(있는 경우), 작업순서 이력 인용은 `change_id`, 보고서 근거 인용은 `report_sources.id`와 그 row의 `source_type + source_id + source_version_id`를 반환한다. `internalSourceUri`는 외부 공개 URL이 아니며, 후속 클라이언트가 사용할 때 원천 권한을 다시 검사해야 한다.

```json
{
  "queryId": "aiq-...",
  "status": "SUCCEEDED",
  "grounded": true,
  "summary": "반복 문제를 확인했습니다.",
  "claims": [
    {
      "claimKey": "claim-1",
      "text": "금형 정렬 재확인이 반복되었습니다.",
      "citations": [
        {
          "candidateId": "candidate-...",
          "sourceType": "FIELD_COMMENT",
          "sourceId": "comment-...",
          "sourceVersionId": "version-...",
          "traceTable": "field_comments",
          "traceId": "comment-...",
          "traceVersionId": "version-...",
          "internalSourceUri": "flownote://field-comments/comment-..."
        }
      ]
    }
  ],
  "responseStored": false,
  "promptVersion": "evidence-summary/v1"
}
```

검색 결과가 없거나 주장을 뒷받침할 수 없으면 HTTP 200으로 `status = INSUFFICIENT_EVIDENCE`, `grounded = false`, `summary = null`, `claims = []`, `reason`을 반환한다. provider 응답에 인용이 없거나 후보 snapshot에 없는 ID가 있거나 일부 사실 주장에 인용이 없으면 해당 본문 전체를 폐기하고 `502 CITATION_VALIDATION_FAILED`를 반환한다. 부분적으로 검증된 문장만 골라 답변처럼 노출하지 않는다. 오류 응답도 `queryId`, 안정된 `error.code`, 한글 `error.message`, `retryable`만 노출하고 provider raw body나 외부 전송 본문은 반환하지 않는다.

`responseStorageMode = DO_NOT_STORE`에서는 응답 본문을 저장하지 않고 SHA-256 hash만 남긴다. `STORE_90_DAYS`는 응답 본문을 저장한다. 두 모드 모두 질의 원문과 `retention_until`, `regenerable_until`을 90일 기준으로 저장하지만, 만료 데이터를 삭제하는 스케줄러는 아직 구현하지 않았다.

검증 테스트 기준:

- 기능 플래그가 꺼진 기본 상태에서 외부 provider client가 한 번도 호출되지 않고 기존 `/api/v1/ai-search/candidates/*`, `/api/v1/ai-search/quality` 테스트가 변경 없이 통과한다.
- 금지 목적은 provider 호출 전에 차단되고 차단 상태와 사유만 호출 시도 row에 남는다. 민감정보/외부 전송 금지 원천 필터는 후속 검증 항목이다.
- 후보가 0건이면 `INSUFFICIENT_EVIDENCE`이고 조언·추정·작업 지시 문구가 반환되지 않는다.
- 성공 응답의 모든 claim은 질의 시점 후보 snapshot에 있는 citation을 한 개 이상 가지며 원천 row와 version/content hash가 일치한다.
- 인용 누락과 snapshot에 존재하지 않는 후보 ID는 응답 전체를 `CITATION_VALIDATION_FAILED`로 처리한다. 원천 상태는 provider 호출 전 snapshot 생성 시점에 재검사하며, 사용자별 원천 권한과 provider 호출 후 상태 재검사는 후속 범위다.
- 현재 테스트는 mock provider로 선택 후보 snapshot과 인용 ID, 응답 미저장을 검증하고 실제 외부 네트워크를 사용하지 않는다. 네 source type별 인용과 인용 실패 경로의 독립 테스트는 후속 보강 항목이다.

## 권한 요약

| 기능 | 허용 role |
| --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` |
| FieldComment 등록 | 위 role + `team-member`, `viewer` |
| 접근 로그 조회 | `admin`, `system-admin` |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| 외부 AI 근거 검색·요약(후속 1단계) | `admin`, `system-admin`. 기능 플래그와 고객·현장별 전송 승인도 필요 |
| 채널 생성/멤버 관리 | 문서/작업순서 쓰기 role. 단, 채널 조회와 메시지/인수인계 조회는 채널 멤버 또는 `admin`, `system-admin` |

WPF `RolePermissionPolicy`와의 대조:

| WPF 기능 | WPF 허용 role | 서버 대응 정책 |
| --- | --- | --- |
| 문서 등록, 파일 업로드, 상태 변경, 공개, 작업판 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | `DocumentWriteUser` |
| 현장 코멘트 작성 | 기본 role 전체 | `FieldCommentCreateUser` |
| 보고서 버튼 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | `ReportWriteUser` |
| 채널 관리/인수인계 확인 현황 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | 채널 생성은 `DocumentWriteUser`, 조회/읽음/수신확인은 채널 멤버십 또는 `admin`, `system-admin` |
| 파일 감시 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | WPF 로컬 기능 |
| 사용자 관리 | `admin`, `system-admin` | 서버 계정 관리 API는 후속 범위 |
| controlled copy 다운로드 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | 서버 다운로드 API는 후속 범위 |

정합성 검증 기준:

- FastAPI `app/core/auth.py`는 `DOCUMENT_WRITE_ROLES`, `FIELD_COMMENT_CREATE_ROLES`, `ACCESS_LOG_READ_ROLES`, `REPORT_WRITE_ROLES`, `USER_MANAGEMENT_ROLES`, `CONTROLLED_COPY_DOWNLOAD_ROLES`를 권한 표의 기준으로 둔다.
- WPF `RolePermissionPolicy`는 같은 role 집합을 문서 등록, FieldComment 작성, 보고서 작성, 접근 로그 조회, 사용자 관리, controlled copy 다운로드 정책으로 검증한다.
- controlled copy 다운로드는 서버 다운로드 API가 아직 없지만, 서버와 WPF 정책 집합은 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`로 고정한다.
- 서버 로그인 성공 시 WPF 현재 세션의 role은 서버 응답 role을 우선하며, 같은 로그인 ID의 로컬 role과 달라도 화면 권한은 서버 role 기준으로 계산한다.
- 서버 401/403 로그인 실패는 WPF 로컬 계정 fallback 금지 대상으로 유지하며 WPF 스모크 테스트에서 확인한다.

## 설정

- `FLOWNOTE_ENVIRONMENT` 또는 `FLOWNOTE_ENV`
- `FLOWNOTE_API_HOST`
- `FLOWNOTE_API_PORT`
- `FLOWNOTE_DATABASE_URL`
- `FLOWNOTE_TEST_DATABASE_URL`
- `FLOWNOTE_DATABASE_ECHO`
- `FLOWNOTE_STORAGE_ROOT`
- `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES`
- `FLOWNOTE_SESSION_COOKIE_NAME`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`
