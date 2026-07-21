# FlowNote API

FastAPI 서버는 `/api/v1` 아래 REST API를 제공한다. 루트 `/`는 서비스 이름과 환경을 반환한다. `/`, `/api/v1/health`, `/api/v1/health/db`, `/api/v1/health/sync-manifest`, `GET /api/v1/sync/manifest`, `GET /api/v1/tags`를 제외한 현재 API는 Bearer token 기반 인증을 요구한다.

이 문서는 2026-07-21 현재 전역 FastAPI 앱에 등록된 method/path 조합과 요청·응답 코드 기준이다. FieldComment 검토/첨부, 보고서 aggregate의 revision/idempotency 계약과 서버 복구 경계 reconciliation API가 구현되어 있다.

## 인증

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 사용자명/비밀번호 로그인, access token과 refresh token 발급. Android는 승인 단말 `deviceId`를 함께 전송 |
| POST | `/api/v1/auth/refresh` | refresh token 검증 후 같은 세션의 access/refresh token 회전 |
| POST | `/api/v1/auth/logout` | 현재 access token 세션을 `REVOKED`로 변경 |
| GET | `/api/v1/auth/me` | 현재 Bearer token 사용자 정보 조회 |
| POST | `/api/v1/auth/change-password` | 본인 현재 비밀번호를 검증하고 새 비밀번호로 변경한 뒤 모든 기존 세션 폐기 |

보호 API는 `Authorization: Bearer {access_token}`을 요구한다. access token은 HMAC 서명 payload이며 서버의 `auth_sessions` 상태와 `access_token_id`까지 검증한다.

`must_change_password = true`인 계정은 로그인 응답에서 같은 값을 받지만 `change-password` 이외의 보호 API와 refresh를 사용할 수 없다. 비밀번호 변경 성공 시 현재 세션을 포함한 모든 활성 세션을 폐기하므로 새 비밀번호로 다시 로그인해야 한다. 최소 비밀번호 길이는 8자이며 현재 비밀번호와 같은 값은 거부한다. 새 비밀번호와 임시 비밀번호 hash는 계정별 무작위 salt를 사용한 PBKDF2-SHA256으로 저장하고 기존 개발 계정 hash도 같은 검증기가 호환한다.

## 서버 계정 수명주기

아래 API는 `admin`, `system-admin`만 사용할 수 있다. `admin`은 일반 계정만 운영하며 system-admin 계정 생성·변경·세션 조회·폐기는 `system-admin`만 가능하다.

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/server-accounts` | 서버 계정 목록 조회. `query`로 로그인 ID/표시 이름 검색 |
| POST | `/api/v1/server-accounts` | 임시 비밀번호와 `must_change_password = true`로 서버 계정 생성 |
| PATCH | `/api/v1/server-accounts/{user_id}` | 표시 이름, role, `ACTIVE`/`LOCKED`/`DISABLED` 상태 변경 |
| POST | `/api/v1/server-accounts/{user_id}/password-reset` | 임시 비밀번호 재설정, 강제 변경 설정, 기존 세션 폐기 |
| GET | `/api/v1/server-accounts/{user_id}/sessions` | 활성 세션 목록. `active_only=false`로 폐기 세션 포함 |
| POST | `/api/v1/server-accounts/{user_id}/sessions/revoke` | 대상 계정의 모든 활성 세션 강제 폐기 |
| POST | `/api/v1/server-accounts/{user_id}/sessions/{session_id}/revoke` | 대상 계정의 특정 활성 세션 강제 폐기 |

계정 생성·변경·재설정·세션 폐기 요청은 필수 `reason`을 받는다. 임시 비밀번호는 요청에서 한 번만 받고 응답, `activity_history`, 일반 애플리케이션 로그에 넣지 않는다. 응답에는 `must_change_password` 상태만 포함한다. 자기 자신을 잠금/비활성화할 수 없고, 마지막 활성 `system-admin`을 비활성화·잠금·다른 role로 변경할 수 없다. role 변경, 비활성화/잠금, 비밀번호 재설정은 대상의 활성 세션을 같은 트랜잭션에서 폐기한다.

모든 계정 변경은 `activity_history`에 `actor_id`, `target_type = user_account`, `target_id`, 비밀번호를 제외한 전후 JSON, 변경 사유, 생성 시각을 기록한다. 이벤트는 `user.created`, `user.updated`, `user.password_reset`, `user.password_changed`, `user.sessions_revoked`, `user.session_revoked`를 사용한다.

운영 기준:

- 서버 로그인은 서버 `user_accounts`의 `is_active`와 `status = ACTIVE`를 모두 만족해야 한다.
- Android 현장 단말 로그인은 `deviceId`가 `terminal_devices.device_id`에 존재하고 `status = ACTIVE`여야 한다. 승인되지 않았거나 비활성 단말이면 403을 반환한다.
- 서버 로그인 성공 시 WPF는 서버 응답의 사용자 ID, 표시 이름, role을 현재 세션 기준으로 사용한다.
- 서버가 로그인 요청에 401 또는 403을 반환하면 WPF는 로컬 계정 로그인으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 WPF 로컬 계정 로그인을 사용한다.
- 서버 PC 운영 스크립트는 비상/초기 운영 경로로 유지하고, 설치형 WPF 운영은 서버 계정 API를 사용한다.
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
| GET | `/` | 서비스 이름과 현재 환경 확인 |
| GET | `/api/v1/health` | API 상태 확인 |
| GET | `/api/v1/health/db` | DB 연결 확인 |
| GET | `/api/v1/health/sync-manifest` | DB 연결 확인 뒤 `status`와 sync manifest 반환 |

## 수렴 제어 API

아래 경로는 WPF 로컬 원천과 서버 권위 원천의 복구·호환 판정을 위한 현재 구현이다. manifest 조회는 인증 없이 사용할 수 있고 reconciliation run 조회·생성·적용과 epoch 증가는 `admin`, `system-admin`만 허용한다.

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/sync/manifest` | `server_instance_id`, `server_epoch`, `schema_contract`, `api_contract_min/max`, `server_cursor` 반환 |
| POST | `/api/v1/sync/reconciliation-runs` | WPF 큐 inventory를 서버 원천과 대조하고 `REVIEW_REQUIRED` run 생성 |
| GET | `/api/v1/sync/reconciliation-runs/{run_id}` | run과 항목별 판정·조치 조회 |
| POST | `/api/v1/sync/reconciliation-runs/{run_id}/apply` | 모든 항목의 판정 조치와 관리자 사유를 확인하고 run을 `APPLIED`로 종결 |
| POST | `/api/v1/sync/server-epoch/increment` | 명시적 복구 경계 표시를 위해 epoch를 1 증가시키고 감사 이력 저장 |

서버는 `server_identity` singleton row의 설치 식별자와 epoch를 manifest에 제공한다. `server_cursor`는 현재 `channel_messages.id` 최댓값이며 메시지가 없으면 0이다. WPF는 서버 URL별 binding을 저장하고 API contract 1이 서버의 `api_contract_min`~`api_contract_max` 범위에 포함되는지 검사한다. 처음 확인한 서버는 활성화하지만, 이미 다른 서버 URL binding이 있는 상태에서 새 URL을 확인하거나 저장한 instance/epoch가 달라지거나 서버 cursor가 로컬 cursor보다 낮으면 `RECONCILIATION_REQUIRED`로 전환한다. 이때 알림 polling과 `server_sync_queue` 자동 전송을 중지하며 기존 mapping, cursor, 처리 `message_id`, 큐를 보존한다.

run 생성 요청은 `clientId`, 선택적 `previousServerInstanceId`·`previousServerEpoch`, `triggerReason`, `clientCursor`, 최대 10,000개의 `items`를 받는다. 각 항목은 `clientItemId`, `entityType`, `localId`, `localVersionNo`, `idempotencyKey`, 선택적 `localHashSha256`·이전 서버 문서/버전 ID를 포함한다. 현재 판정 대상은 `document`, `document_version`, `field_comment`, `field_comment_attachment`, `document_access_log`, `report`다. 응답 결과와 제안 조치는 다음 셋이다.

| 결과 | 의미 | WPF 조치 |
| --- | --- | --- |
| `CONFIRMED` / `REBOUND` | 같은 idempotency key가 있고 제공된 hash도 일치 | 응답의 현재 server ID/revision/hash로 mapping 재결합하고 큐를 `SYNCED`로 종결 |
| `ABSENT` / `REQUEUE` | 같은 idempotency key의 서버 row가 없음 | 기존 큐의 서버 ID를 비우고 `PENDING`으로 되돌려 동일 key로 재전송 |
| `DIVERGED` / `CONFLICT` | 지원하지 않는 entity이거나 비교 hash 부재·불일치 | 큐를 `DISCARDED`로 종결하되 `RECONCILIATION_DIVERGED`, 상세, 해결자·시각을 보존 |

run 생성은 업무 도메인 원천을 수정하지 않고 서버와 WPF 양쪽에 판정 이력을 추가한다. 적용 요청은 run의 모든 항목을 한 번씩 포함하고 각 `action`이 서버 제안 조치와 같아야 한다. 서버는 승인자·항목별 사유·승인 사유와 `sync.reconciliation.approved` 활동 이력을 저장한다. 그 응답을 받은 WPF는 한 로컬 transaction에서 큐·mapping·binding을 갱신하고 해당 서버 scope의 알림 cursor를 0으로 되돌려 재추적한다. 기존 처리 `message_id`는 삭제하지 않는다. 이후 `PENDING` 재전송을 재개한다.

공통 오류 응답의 `detail`은 `code`, `message`, `retryable`, 선택적 `currentRevision`, `currentEntityId`, `serverEpoch`를 갖는다. 처리 규칙은 다음과 같다.

| HTTP/code | 자동 재시도 | 규칙 |
| --- | --- | --- |
| 401/403 | 아니요 | 현재 묶음 중단, 로그인/권한 해결. 로컬 원천 보존 |
| 409 `STALE_*`, `*_CHANGED`, `*_ORPHAN`, `IDEMPOTENCY_KEY_REUSED`, `SERVER_RECOVERY_DIVERGED` | 아니요 | `CONFLICT` 저장, 최신값 추정·자동 병합 금지 |
| 422 | 아니요 | payload/로컬 원천 검증 실패를 보존 `FAILED`로 기록 |
| 426 `CLIENT_CONTRACT_UNSUPPORTED` | 아니요 | 앱/서버 호환 버전 조정 전 sync 중지 |
| 503 `SCHEMA_MIGRATION_IN_PROGRESS` 또는 일시 장애 | 예 | `Retry-After` 우선, 없으면 5초~5분 exponential backoff+jitter |
| timeout/연결 끊김/응답 유실 | 예 | 동일 idempotency key와 intent hash 재사용 |

서버가 2xx를 반환해도 WPF가 서버 결과 ID·revision·hash와 로컬 mapping을 같은 transaction에 저장하기 전에는 `SYNCED`가 아니다. 같은 idempotency key가 서버 도메인 테이블 또는 mutation receipt에 둘 이상 존재하면 서버 health와 reconciliation은 실패해야 한다.

## 문서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/documents` | multipart 문서와 최초 버전 등록 |
| GET | `/api/v1/documents` | 전체 문서 목록 |
| GET | `/api/v1/documents/published` | 공개 문서 목록 |
| GET | `/api/v1/documents/{document_id}` | 문서 상세 |
| GET | `/api/v1/documents/{document_id}/published` | 공개 버전 조회 |
| PUT | `/api/v1/documents/{document_id}/tags` | `baseRevision` query 기준이 일치할 때 문서 태그 교체 |
| PATCH | `/api/v1/documents/{document_id}/status` | JSON `baseRevision` 기준 문서 상태 변경 |
| GET | `/api/v1/documents/{document_id}/versions` | 문서 버전 목록 |
| POST | `/api/v1/documents/{document_id}/versions` | 새 파일 버전 등록. multipart `idempotencyKey`를 보내면 같은 키의 재시도는 기존 버전을 반환 |
| PATCH | `/api/v1/documents/{document_id}/versions/{version_id}/status` | JSON `baseRevision` 기준 버전 상태 변경 |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/publish` | JSON `baseRevision`과 예상 공개본 기준으로 특정 버전을 공개 버전으로 지정 |
| DELETE | `/api/v1/documents/{document_id}` | `baseRevision`, `changeReason`으로 문서를 soft delete. 공개 포인터 해제와 감사를 함께 저장 |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/controlled-copy` | 현재 공개 버전의 1회성 controlled copy 티켓 발급 |
| GET | `/api/v1/controlled-copies/{token}` | 발급 사용자·로그인 세션에 묶인 controlled copy 1회 스트리밍 |
| POST | `/api/v1/documents/{document_id}/versions/{version_id}/android-view-grants` | 승인 Android 단말의 현재 공개 버전 앱 내부 열람 grant 발급 |
| GET | `/api/v1/android-document-views/{token}/stream` | 사용자·세션·승인 단말에 묶인 Android 본문 1회 `inline` 스트리밍 |

문서 생성 시 허용되는 상태는 `WORKING`, `IN_REVIEW`, `ARCHIVED`이다. `PUBLISHED`는 publish 엔드포인트로만 만든다.

문서 응답과 목록은 서버 권위의 `revision`을 포함한다. 버전 등록 multipart는 `baseRevision`, `baseVersionId`, `fileHashSha256`, `idempotencyKey`를 받을 수 있다. WPF는 네 값을 모두 보내며 서버는 최신 버전 ID와 revision을 원자적으로 비교한 뒤 새 버전 번호를 배정한다. publish JSON은 `baseRevision`, `expectedPublishedVersionId`, `changeReason`, 문서 상태 JSON은 `baseRevision`, `status`, `changeReason`, 버전 상태 JSON도 `baseRevision`, `status`, `changeReason`을 사용한다. 태그 전체 교체는 필수 `baseRevision` query가 맞을 때만 수행한다.

문서 버전 등록의 선택적 `idempotencyKey`는 공백을 제거한 뒤 최대 160자로 제한하며 서버 `document_versions.idempotency_key`에 유일하게 저장한다. 같은 키·같은 파일 hash를 같은 문서에 다시 보내면 새 파일이나 버전을 만들지 않고 기존 버전을 반환한다. 다른 문서 사용, 같은 키의 다른 파일 또는 최초 문서 등록의 핵심 메타데이터 불일치는 409 `IDEMPOTENCY_KEY_REUSED`다. 특정 버전 publish도 이미 그 버전이 현재 공개 버전이고 문서·버전 공개 상태가 일치하면 revision을 다시 올리지 않고 현재 문서를 반환한다.

동기화 충돌은 HTTP 409와 아래 `detail` 구조를 사용한다.

```json
{
  "detail": {
    "code": "STALE_REVISION",
    "message": "The document changed after the client base revision. Administrator resolution is required.",
    "documentId": "doc_...",
    "expectedRevision": 4,
    "currentRevision": 5,
    "currentStatus": "PUBLISHED",
    "currentLatestVersionId": "ver_...",
    "currentPublishedVersionId": "ver_..."
  }
}
```

충돌 코드는 `STALE_REVISION`, `STALE_BASE_VERSION`, `PUBLISHED_VERSION_CHANGED`, `DOCUMENT_DELETED`, `IDEMPOTENCY_KEY_REUSED`, `FILE_HASH_MISMATCH`를 구분한다. WPF 구 공개/상태 큐에 서버 기준 revision이 없으면 서버 호출 전에 `LEGACY_BASE_MISSING` 충돌로 전환한다. 클라이언트는 이를 자동 일반 재시도하지 않고 충돌 작업함에 보존한다. 네트워크 단절·timeout은 409가 아니므로 안정된 idempotency key로 재시도한다.

controlled copy는 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 요청할 수 있다. 서버는 요청 시점과 전송 시점에 문서가 삭제되지 않은 `PUBLISHED` 상태인지, 요청 버전이 `published_version_id`와 일치하고 `version_status = PUBLISHED`, `is_published = true`인지 다시 검사한다. 티켓은 기본 60초, 최대 300초이며 발급 사용자와 `auth_sessions.session_id`에 묶이고 첫 전송 시 소비된다. 다른 사용자·다른 로그인 세션, 만료, 재사용은 거부한다.

응답은 상대 `download_url`, 파일명, MIME type, 크기, SHA-256만 포함하며 `storage_key`와 로컬 원본 경로를 포함하지 않는다. 스트리밍 응답은 `Content-Disposition: attachment`, `Content-Length`, `X-Content-SHA256`, `Cache-Control: no-store`, `Accept-Ranges: none`을 사용한다. Range 요청은 티켓을 소비하고 416으로 거부한다. 서버는 저장 키가 절대 경로나 `..`를 포함하지 않고 설정된 `storage_root` 아래로 해석되는지 검사하며, 기본 500 MiB 크기 제한과 등록 SHA-256을 발급 전·전송 전에 확인한다.

Android secure view grant는 `system-admin`을 제외한 현장·문서 운영 role인 `admin`, `manager`, `viewer`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`, `team-member`에게만 발급한다. role 허용만으로 충분하지 않고 로그인 세션에 `device_id`가 있으며 해당 `terminal_devices.status = ACTIVE`여야 한다. 발급과 스트림 직전에 사용자·세션·단말, 현재 `PUBLISHED` 문서와 정확한 `published_version_id`, 파일 경계·크기·등록 SHA-256을 다시 검사한다. 공개 해제·새 버전 공개·계정/세션/단말 비활성화 후 기존 grant는 사용할 수 없다.

grant 응답은 `grant_id`, 상대 `stream_url`, 문서/버전 ID, 만료 시각, `media_kind`(`PDF`, `IMAGE`, `TEXT`), MIME type, 크기, SHA-256, PDF 페이지 한도, TXT 크기 한도, 자동 닫힘 초를 반환한다. 실제 파일명과 `storage_key`는 반환하지 않는다. 기본 grant 만료는 60초이고 5~300초로 정규화하며 1회 소비한다. 스트림은 `Content-Disposition: inline`, `Cache-Control: no-store, private, max-age=0`, `X-Content-SHA256`, `Accept-Ranges: none`, `X-Content-Type-Options: nosniff`를 사용한다.

허용 형식은 UTF-8 `.txt`, `.pdf`, `.png`, `.jpg`/`.jpeg`, `.webp`이다. 기본 전체 크기 한도는 50 MiB, TXT는 5 MiB, PDF는 200쪽이며 환경 변수 `FLOWNOTE_ANDROID_VIEW_MAX_BYTES`, `FLOWNOTE_ANDROID_VIEW_MAX_TEXT_BYTES`, `FLOWNOTE_ANDROID_VIEW_MAX_PDF_PAGES`로 조정한다. 확장자/MIME 불일치, 미지원 형식과 기본 손상 검사는 415, 크기 초과는 413이다. 권한·단말 거부는 403, 만료·재사용은 410, 발급 뒤 공개 상태나 파일 무결성 변경은 409로 응답한다. 네트워크가 끊겨 1회 스트림이 중단되면 앱은 부분 파일을 제거하고 새 grant를 요청해야 한다.

## 접근 로그

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/documents/{document_id}/access-logs` | 문서 접근 로그 등록 |
| GET | `/api/v1/documents/{document_id}/access-logs` | 문서 접근 로그 조회 |

`action` 값은 `view_started`, `view_closed`, `download_blocked`, `auto_closed`, controlled copy 이벤트와 Android의 `android_view_granted`, `android_view_stream_started`, `android_view_completed`, `android_view_failed`, `android_view_blocked`, `android_view_expired`를 사용한다. 두 계약의 이벤트는 사용자, 세션에 연결된 단말, 문서 버전, IP, user agent, 사유를 `document_access_logs`와 `activity_history`에 함께 남긴다. 존재하지 않는 문서는 외래키로 문서 접근 로그를 만들 수 없으므로 요청 ID와 사유를 `activity_history`에 남긴다. 조회는 `admin`, `system-admin`만 가능하다.

## FieldComment

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/field-comments` | FieldComment 원천 기록 등록 |
| GET | `/api/v1/field-comments` | FieldComment 목록 조회 |
| GET | `/api/v1/field-comments/{comment_id}` | FieldComment 상세 조회 |
| PATCH | `/api/v1/field-comments/{comment_id}` | 상태, 정리 내용, 분석 내용 갱신 |
| POST | `/api/v1/field-comments/bulk-review` | 최대 200건 담당 지정·기한·상태 일괄 변경 |
| GET | `/api/v1/field-comments/{comment_id}/audit` | 원천 hash를 포함한 검토 변경 전·후 감사 snapshot |
| GET | `/api/v1/field-comments/{comment_id}/traceability` | FieldComment, 감사, report source, 생성 최종 문서·버전 통합 역추적 |
| GET | `/api/v1/field-comments/quality-workbench` | 오래된 NEW, 근거가 빈약한 SELECTED, 원천·trace/version 누락, source hash 불일치 작업함 |
| GET | `/api/v1/field-comments/quality-metrics` | 상태·신호등·actor·라인·오류 유형 분포와 보고서 연결률 |
| POST | `/api/v1/field-comments/{comment_id}/attachments` | 첨부 파일 등록. multipart `idempotencyKey`를 보내면 같은 키의 재시도는 기존 첨부를 반환 |
| GET | `/api/v1/field-comments/{comment_id}/attachments` | 첨부 파일 목록 조회 |
| GET | `/api/v1/documents/{document_id}/field-comments` | 특정 문서의 FieldComment 조회 |

FieldComment는 `documentId`, `structureItemId`, `workRecordId` 중 하나 이상을 참조해야 한다. 현재 구조에서는 문서 참조가 주 사용 경로다.

FieldComment 원천 삭제 API는 제공하지 않는다. 서버 ORM도 `field_comments` row 삭제를 거부하므로 오입력·중복·근거 부적합은 삭제 대신 사유를 남겨 `EXCLUDED`로 전이한다.

첨부 등록의 선택적 `idempotencyKey`도 공백을 제거한 뒤 최대 160자로 제한하며 서버 `field_comment_attachments.idempotency_key`에 유일하게 저장한다. WPF는 multipart `parentCommentId`, `fileSha256`, `idempotencyKey`를 함께 보낸다. `parentCommentId`가 경로의 FieldComment와 다르면 409 `ATTACHMENT_PARENT_MISMATCH`, `fileSha256`이 64자 SHA-256 hex가 아니면 422, 저장 파일의 서버 계산 hash와 다르면 파일을 제거하고 409 `ATTACHMENT_FILE_HASH_MISMATCH`로 응답한다. 같은 키를 같은 FieldComment와 같은 파일 hash로 다시 보내면 새 파일·첨부 row를 만들지 않고 기존 첨부와 file object를 반환한다. 다른 FieldComment 또는 다른 파일 hash에 키를 재사용하면 409로 거부한다. WPF 재시도 큐는 문서 버전과 FieldComment 첨부 전송에도 큐의 안정된 idempotency key를 그대로 전달한다.

`GET /api/v1/field-comments`는 관리자 검토 화면 기준으로 `status`, `documentId`, `documentText`, `author`, `assignedTo`, `tag`, `line`, `equipment`, `process`, `errorType`, `createdFrom`, `createdTo`, `oldNewDays`, `hasAttachments`, `reportLinked`, `unreviewed`, `overdue`, `unassigned`, `missingEvidence`, `duplicateSuspected`, `priorityOrder`, `limit` 필터를 지원한다. 응답의 `workbench_flags`, `workbench_priority`는 관리자 처리 순서를 설명한다. WPF 관리자 화면은 같은 기준으로 로컬 `field_comments`, 문서, 문서 태그, 첨부와 보고서 source를 함께 조회한다.

상태 변경은 `transitionReason` 3자 이상이 필수다. 주 흐름은 `NEW → ANALYZED → REVIEWED → SELECTED`이며 정해진 한 단계 전진과 감사 가능한 되돌림만 허용한다. 서버는 요청의 `reviewedBy`·`analyzedBy`를 신뢰하지 않고 인증 actor를 기록한다. `SELECTED`는 정리·분석 내용과 원천 작성자·문서 버전이 있어야 한다. 세부 권한과 되돌림 표는 [FieldComment 검토·분석·선정 운영](./field-comment-review-workflow.md)을 따른다.

WPF 관리자 검토 화면은 선택한 FieldComment의 `normalized_content`, `analysis_content`, `status`를 수정하고 `server_sync_queue`에 `entity_type = field_comment_review`, `action = update_field_comment_review`로 서버 PATCH 재시도 항목을 남긴다. 서버 ID가 아직 없는 로컬 FieldComment는 선행 등록 동기화가 끝난 뒤 검토 변경 PATCH를 재시도한다.

FieldComment 응답은 원천 `source_hash_sha256`와 서버 권위 `review_revision`을 반환한다. 검토 PATCH의 `baseReviewRevision`, `mutationKey`는 선택 필드지만 WPF는 큐 생성 시 읽은 revision과 안정된 큐 key를 항상 보낸다. 서버는 조건부 UPDATE로 base revision과 현재 revision이 같은 요청 하나만 성공시키고 revision을 1 증가시키며, 검토 변경과 `field_comment_review_mutation_receipts`를 같은 transaction에 저장한다. 같은 key·같은 comment·같은 intent 재시도는 영수증의 최초 응답 snapshot을 반환한다. 같은 key의 다른 comment/intent는 409 `IDEMPOTENCY_KEY_REUSED`, revision 불일치는 현재 revision을 포함한 409 `FIELD_COMMENT_STALE_REVIEW_REVISION`이다. `baseReviewRevision`을 생략한 직접 API 요청은 서버가 조회한 현재 revision을 기준으로 처리하므로 클라이언트가 읽은 시점의 낙관적 잠금을 제공하지 않는다. WPF는 서버 상태를 따라잡기 위해 중간 상태를 자동 생성하지 않는다.

`POST /api/v1/field-comments/bulk-review`도 각 대상의 현재 `review_revision`을 조건부 갱신해 1씩 증가시킨 뒤 기존 상태 전이 정책을 적용한다. 이 일괄 요청에는 항목별 base revision이나 mutation key/receipt가 없으며, 대상 누락이나 항목 하나의 검증·동시성 갱신 실패가 있으면 전체 transaction을 저장하지 않는다.

## 태그

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/v1/tags` | 태그 목록 조회 |
| POST | `/api/v1/tags` | 태그 생성 |

태그 타입은 `equipment`, `item`, `process`, `error_type`, `line`, `location`, `custom`을 허용한다.

## 작업순서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/work-sequence-boards` | 작업순서 보드 생성. `idempotencyKey` 필수 |
| GET | `/api/v1/work-sequence-boards` | 작업순서 보드 목록. `lineCode`, `status` 필터 선택 |
| GET | `/api/v1/work-sequence-boards/{board_id}` | 작업순서 보드와 정렬된 항목 상세 |
| POST | `/api/v1/work-sequence-boards/{board_id}/items` | 항목 추가. `idempotencyKey`, `baseBoardRevision` 필수 |
| PUT | `/api/v1/work-sequence-boards/{board_id}/items/order` | 항목 전체 순서 변경. 전체 item ID와 `idempotencyKey`, `baseBoardRevision` 필수 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/items/{item_id}/status` | 항목 상태·보류 사유 변경. `idempotencyKey`, `baseBoardRevision` 필수 |
| GET | `/api/v1/work-sequence-boards/{board_id}/history` | mutation key·적용 revision을 포함한 변경 이력 조회 |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | 알림 후보 조회 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | 알림 후보 상태 변경 |

작업순서는 서버 직접 운영으로 확정한다. WPF는 연결된 서버의 목록·상세를 읽고 mutation API를 직접 호출하며 새 작업순서 mutation을 로컬 `server_sync_queue`에 넣지 않는다. 서버가 없거나 호환 contract를 만족하지 못하면 로컬 초안 조회는 가능하지만 생성·순서·상태의 운영 확정은 비활성화한다.

구현된 계약에서 보드 상세와 목록 응답은 `board_revision`을 포함한다. 보드 생성, 항목 추가, 전체 순서 변경, 항목 상태 변경은 `idempotencyKey`를 필수로 받고 기존 보드 mutation은 `baseBoardRevision`도 필수로 받는다. 생성 revision은 1이며 항목 추가·순서·상태의 의미 있는 변경마다 조건부로 정확히 1 증가한다. 같은 revision의 경쟁 요청은 조건부 갱신에 성공한 한 요청만 저장되고 나머지는 409 `WORK_SEQUENCE_STALE_REVISION`과 `expectedRevision`, `currentRevision`을 받는다. 쓰기는 문서 편집 권한 role, 조회는 인증된 사용자를 요구한다.

서버는 보드/항목 mutation, 정확히 한 `work_sequence_change_history` row와 `work_sequence_mutation_receipts` row를 같은 transaction에 저장하고, 순서·상태 변경처럼 알림 대상인 경우 notification candidate도 함께 저장한다. 상태와 보류 사유를 함께 바꾸어도 `ITEM_STATUS_CHANGED` 이력 1건만 만든다. 같은 key·같은 intent의 재요청은 receipt에 보존된 최초 성공 응답을 반환하고 revision·이력·알림을 다시 만들지 않는다. 같은 key를 다른 intent에 쓰면 409 `IDEMPOTENCY_KEY_REUSED`다. 현재 순서나 상태와 같은 no-op 요청은 422로 거부하여 revision과 이력을 소비하지 않는다.

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
| PATCH | `/api/v1/notifications/{message_id}/read` | 현재 사용자의 해당 채널 메시지 읽음 처리. Android는 선택 `deliveryRunId`, `displayedAt` 증거 포함 |
| POST | `/api/v1/handovers` | 인수인계 등록, 수신자별 receipt 생성, 채널 메시지 생성 |
| GET | `/api/v1/handovers` | 현재 사용자가 속한 채널의 인수인계 목록 |
| GET | `/api/v1/handovers/{handover_id}` | 인수인계 상세와 수신자별 receipt 조회 |
| PATCH | `/api/v1/handovers/{handover_id}/receipts/{receipt_id}` | 수신자별 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 상태와 선택 `deliveryRunId`, `displayedAt` 기록 |
| GET | `/api/v1/work-sequence-boards/{board_id}/notification-candidates` | 작업순서 변경으로 생성된 알림 후보 조회 |
| PATCH | `/api/v1/work-sequence-boards/{board_id}/notification-candidates/{candidate_id}` | 작업순서 알림 후보 상태를 `CANDIDATE`, `SENT`, `DISMISSED` 중 하나로 변경 |

채널 유형은 `LINE`, `EQUIPMENT`, `PROCESS`, `WORK_GROUP`, `HANDOVER`, `WORK_RECORD`, `CUSTOM`이다. 채널 메시지 유형은 `NOTICE`, `DOCUMENT_EVENT`, `FIELD_COMMENT_EVENT`, `WORK_SEQUENCE_EVENT`, `HANDOVER`, `SYSTEM`이다. 인수인계 상태는 `DRAFT`, `SENT`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`, `ARCHIVED`이고, 수신 상태는 `UNREAD`, `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`이다.

채널 메시지와 인수인계는 `sourceType`, `sourceId`, `sourceVersionId`로 원천을 추적한다. 메시지 source는 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `REPORT`, `HANDOVER`, `SYSTEM`을 허용한다. 인수인계 source는 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `REPORT`, `CHANNEL_MESSAGE`를 허용한다.

알림 증분 조회 계약은 다음과 같다.

- `afterId`는 마지막으로 처리 완료한 응답 항목의 정수 `cursor`다. 생략하면 최신순 목록, 지정하면 `cursor > afterId`인 항목을 cursor 오름차순으로 반환한다.
- `limit`은 1~500이고 기본값은 100이다. `unreadOnly` 기본값은 `false`이며 필터 적용 후 limit을 계산한다.
- 응답의 `cursor`는 서버 `channel_messages`의 단조 증가 식별자이고 `message_id`는 사용자 표시와 읽음 처리의 공개 멱등 키다. 생성 시각은 cursor 경계로 사용하지 않는다.
- 응답 헤더 `X-FlowNote-Notification-Cursor`는 서버 `channel_messages` 전체의 현재 high-water cursor이며 메시지가 없으면 `0`이다. `X-FlowNote-Next-Cursor`는 이번 응답에서 안전하게 확정할 마지막 cursor(빈 page면 요청 `afterId`), `X-FlowNote-Has-More`는 page가 limit에 도달했는지를 반환한다. 클라이언트는 항목 처리 뒤 `Next-Cursor`까지만 전진하고, 저장값보다 낮은 high-water는 서버 DB 복구/초기화 의심 상태로 다룬다.
- 응답 항목을 표시·보존한 직후 해당 cursor를 원자적으로 저장한다. 응답 도중 실패하면 마지막 확정 cursor로 다시 조회한다. Android 시스템 알림은 `message_id` 기반 고정 notification ID로 교체하고, 서버 읽음과 receipt는 공개 `message_id` 및 유일한 `receipt_id` row를 반복 갱신해 중복 row를 만들지 않는다.
- 인수인계 등록은 `message_type = HANDOVER`, `source_id = handover_id`인 채널 메시지를 함께 만들므로 같은 알림 증분 스트림으로 전달된다. receipt 갱신은 동일 `receiptStatus`와 `note`를 반복 요청해도 추가 상태 변경 이력을 만들지 않으며 현재 receipt를 반환한다. timeout에는 같은 receipt ID와 동일 payload로 재시도한다.
- Android는 service 실행마다 `ANDROID-DELIVERY-{uuid}` run ID를 만들고 알림 표시 시각을 로컬 전달 로그에 남긴다. 읽음 JSON의 `deliveryRunId`/`displayedAt`, receipt JSON의 `deliveryRunId`/`displayedAt`은 선택 필드이며 제공되면 `activity_history.after_value`의 JSON 증거에 서버 처리 시각과 함께 저장한다. token이나 알림 본문은 이 증거에 저장하지 않는다.
- 멤버십이 `ACTIVE`인 현재 사용자 채널만 반환한다. 권한 없는 채널 및 다른 사용자의 알림은 cursor 범위에 있어도 반환하지 않는다.

채널 생성과 메시지 등록은 서버 인증이 필요하다. 채널 생성은 문서/작업순서 쓰기 role 기준을 사용하며, 채널 조회, 메시지 조회, 인수인계 조회는 채널 멤버 또는 `admin`, `system-admin`만 가능하다. 수신확인은 해당 receipt 수신자 또는 `admin`, `system-admin`만 변경할 수 있다. 개인 DM, 개인 메신저 수집, GPS, 근태 기능은 이 API에 포함하지 않는다.

## 보고서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/reports/drafts` | 수동 보고서 초안 생성 |
| POST | `/api/v1/reports` | 보고서 저장, 선택 시 문서로 저장. `idempotencyKey`를 보내면 같은 키의 재시도는 기존 보고서를 반환 |
| GET | `/api/v1/reports` | 보고서 목록 |
| GET | `/api/v1/reports/{report_id}` | 보고서 상세 |

보고서 draft와 최종 저장은 서로 다른 `sourceType` 최소 2종을 요구하며 같은 type/id/version 중복을 거부한다. 응답의 각 source는 `source_type`, `source_id`, 고정 `source_version_id`, 독립 `trace_id`, 저장 시점 `source_hash_sha256`를 반환한다. 최종 승인 직전에 같은 version의 원천 hash를 다시 계산하며 불일치하면 `409`로 차단한다. 승인된 보고서의 draft ID로 source를 교체할 수 없고 동일 `idempotencyKey` 재시도는 기존 보고서·생성 문서·source를 반환한다.

보고서 source 타입은 `FIELD_COMMENT`, `DOCUMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `WORK_RECORD_VERSION`을 사용한다. 서버 저장은 `SELECTED` FieldComment와 현재 공개 문서 버전만 허용하며 FieldComment의 관찰 문서 버전을 source에 자동 고정한다. 활성 업무 채널에 연결된 source는 actor의 활성 멤버십을 검사한다. 현재 WPF 로컬 초안 후보도 `SELECTED` FieldComment, 공개 문서, 작업순서 항목/이력만 노출하며, `SELECTED` 전이에는 관찰 문서 버전과 원천 작성자가 필요하다.

구현된 보고서 저장 계약은 `idempotencyKey`, `mutationKey`, 기존 초안의 선택적 `baseReportRevision`, 선택적 `contentHashSha256`, `sourceSetHashSha256`을 받는다. 각 source 요청은 `sourceType`, `sourceId`, 선택적 `sourceVersionId`, `relationType`을 보내며 서버가 현재 원천을 검증해 `source_hash_sha256`를 고정한다. 내용 hash는 보고서 유형·제목·본문·작업/구조/기간·상태의 정규화 JSON, source 집합 hash는 source type/ID/version/hash/relation의 정렬 canonical JSON을 SHA-256으로 계산한다. 기존 초안 저장은 base revision의 조건부 UPDATE가 성공할 때 `report_revision`을 1 증가시킨다. `baseReportRevision`을 생략하면 서버가 조회한 현재 revision을 사용하므로 클라이언트가 읽은 시점의 낙관적 잠금을 제공하지 않는다.

서버는 문서/파일 생성 직전에 모든 source의 존재·상태·version·hash와 채널 권한을 다시 읽는다. 변경되거나 사라진 원천은 409 `REPORT_SOURCE_STALE_OR_ORPHAN`, 기존 초안 revision 경합은 409 `REPORT_STALE_REVISION`, 클라이언트가 보낸 두 hash와 서버 계산값 불일치는 각각 `REPORT_CONTENT_HASH_MISMATCH`, `REPORT_SOURCE_SET_HASH_MISMATCH`다. `mutationKey`가 없으면 `idempotencyKey`를 mutation key로 사용하며 같은 key·같은 intent는 `report_mutation_receipts`의 최초 응답을 반환하고 다른 intent는 409 `IDEMPOTENCY_KEY_REUSED`다. 보고서, source, 선택적 생성 document/version, 두 hash와 mutation receipt는 한 transaction으로 확정된다. 응답은 `report_revision`, `content_hash_sha256`, `source_set_hash_sha256`, `generated_document`와 source별 확정 ID/version/hash를 반환한다. 현재 WPF는 report/document/version ID를 로컬에 매핑한 뒤 큐를 `SYNCED`로 종결하지만 응답의 report revision과 두 hash를 로컬에 보존하거나 enqueue 시 source-set hash와 대조하지는 않는다.

## AI 검색 근거 후보

AI 검색 후보 API는 자동 조언이 아닌 “근거가 있는 검색과 요약”의 read model 관리 범위다. 이 API는 외부 AI 기능 플래그와 독립적으로 재생성·조회·품질 점검을 계속한다. 실제 외부 provider 네트워크 호출, 자동 작업지시 변경, 자동 의사결정은 포함하지 않는다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/ai-search/candidates/rebuild` | 현재 DB 기준으로 검색 후보를 재생성하고 후보 수와 제외 사유를 반환 |
| GET | `/api/v1/ai-search/candidates` | 검색 후보 목록 조회. `sourceType`, `sourceId`, `limit`으로 제한 가능 |
| GET | `/api/v1/ai-search/quality` | 후보 수, 원천별 개수, 제외 사유, FieldComment 검토 상태 부족분과 최근 회귀 평가 요약 조회 |
| POST | `/api/v1/ai-search/evaluations` | 외부 AI 호출 없이 질문별 기대 근거와 실제 후보를 비교하고 재현성 snapshot을 누적 저장 |
| POST | `/api/v1/ai-search/ground-truth-cases` | 범주·유형·근거·순위·시점과 데이터 분류/provenance를 첫 승인 상태로 저장. 아직 비활성 |
| POST | `/api/v1/ai-search/ground-truth-cases/{ground_truth_case_id}/second-approval` | 첫 승인자와 다른 권한 사용자가 고정 근거와 접근권한을 다시 검증해 사례를 활성화 |
| GET | `/api/v1/ai-search/ground-truth-cases` | 현재 scope의 질문 조회. 기본은 활성 승인 사례만 반환하고 운영용 `includePending=true`이면 미승인 사례도 포함한다. `lineScope`가 없으면 현장 공통 사례, 있으면 해당 라인 사례만 조회 |
| GET | `/api/v1/ai-search/readiness` | 고객·현장·선택적 라인·DB scope별 네 원천 수, 승인 질문 48건 및 범주×유형별 2건 부족분, 품질 임계값, provider 심사와 착수 가능 여부 조회 |

검색 후보 원천은 `PUBLISHED_DOCUMENT_VERSION`, `FIELD_COMMENT`, `WORK_SEQUENCE_HISTORY`, `REPORT_SOURCE` 네 종류만 허용한다. 각 후보 응답은 안정된 `candidate_id`, `content_hash`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `parent_type`, `parent_id`를 포함해 원문 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 근거 row로 역추적할 수 있어야 한다. `candidate_id`는 source type/id/version 조합의 결정적 hash이며 원천 내용이 바뀌지 않으면 재생성 뒤에도 유지되고, 검색 본문 변경은 `content_hash`로 구분한다.

평가 요청은 `runLabel`, 선택적 `evaluateAsUserId`, `lineScope`, `groundTruthCaseIds[]`, 호환용 임시 `cases[]`를 받는다. 승인 사례 평가는 현재 고객·현장·라인·DB scope가 일치하는 활성 ID만 허용하고 `FIELD_READINESS`와 `SMOKE_REGRESSION`을 한 run에 섞지 않는다. 각 case에는 `caseKey`, `question`, `expectedOutcome`, `expectedEvidence[]`, `expectedExcluded[]`, `allowedRankMin`, `allowedRankMax`, `asOf`, `limit`을 둔다. ground-truth 생성 요청에는 `dataClassification`, `provenanceNote`가 필수이며 각 포함 reference는 `rationale`, 각 제외 reference는 `rationale`과 `exclusionReason`이 필수다. 승인 시 포함 근거는 실제 candidate와 원본 version/trace row, content hash, 승인자의 접근권한, `as_of`를 검증해 snapshot으로 고정하며 제외 근거도 실제 원천 row와 hash를 고정한다. 서버는 후보를 두 번 재생성해 ID·content hash와 순위를 비교하고 결과를 누적 저장한다. run 응답은 준비도 계열과 질문별·전체 `precision_at_k`, `recall_at_k`, `top_k_inclusion_rate`, `excluded_source_violation`, `permission_leak_violation`, `nonexistent_citation_violation`, `citation_trace_success_rate`, `citation_semantic_match_rate`, `conflict_disclosure_rate`를 포함한다. 질문과 일치하는 적격 후보가 없으면 답변을 만들지 않고 `INSUFFICIENT_EVIDENCE`로 판정한다. 채널에 연결된 원천은 평가 사용자에게 활성 멤버십이 없으면 `CHANNEL_ACCESS_DENIED`로 제외한다. 이 API는 provider client를 호출하지 않는다.

`GET /api/v1/ai-search/readiness`는 `field_readiness`와 `smoke_regression_readiness`를 별도 반환한다. provider 착수 가능은 실제 현장 계열에서 문서 10, 검토 가능한 FieldComment 100, 작업순서 이력 20, 보고서 source 10 후보와 독립 2인 승인 질문 48건을 요구한다. 여덟 범주와 `NORMAL`/`EXCLUSION`/`CONFLICT`의 24개 조합은 각각 2건 이상이어야 한다. 같은 scope의 실제 현장 승인 세트 전체 평가에서 candidate ID/content hash와 순위가 안정되고 top-k 포함률·인용 trace·인용 의미 일치율·상충 표시율이 모두 100%, 제외 근거 노출·권한 누출·존재하지 않는 인용이 각각 0건이어야 한다. 스모크 48건이 통과해도 실제 현장 건수로 합산하지 않는다. 현재 provider/model의 기술·보안·법무·고객 심사와 필수 체크리스트까지 모두 승인되어야 `provider_start_ready=true`다. DB scope는 로컬 경로나 자격정보를 반환하지 않는 driver+hash 식별자다. `FLOWNOTE_AI_READINESS_GATE_ENABLED` 기본값은 `true`이며 미달 scope는 provider 호출 전에 `409 AI_READINESS_NOT_MET`로 차단한다. 이 판정은 외부 전송 승인이나 기능 플래그를 자동으로 켜지 않는다.

WPF `AI 근거 후보 운영 점검` 화면은 `POST /api/v1/ai-search/candidates/rebuild`로 후보를 재생성한 뒤 `GET /api/v1/ai-search/quality`의 후보/제외/FieldComment 검토 지표와 `GET /api/v1/ai-search/readiness`의 서버 고객·현장·DB scope, 네 원천과 승인 질문 부족분, 범주/유형 누락, 운영 호출 차단 상태를 표시한다. 화면은 이 수치가 서버 DB 기준이며 WPF 공통 로컬 SQLite와 합산되지 않음을 명시한다. 후보 목록에서 운영자는 `trace_table`, `trace_id`, `trace_version_id`로 원문 문서 버전, FieldComment, 작업순서 이력, 보고서 source row로 이동해 근거를 확인하며 선택 후보의 추적값을 클립보드에 복사할 수 있다.

WPF `AI 정답셋 > 사례·원천 구성` 창은 후보 목록에서 포함 근거를 선택하고 제외 원천 ID·선택적 version ID·제외 사유·근거 설명을 입력해 `POST /ground-truth-cases`를 호출한다. 사례 등록/2차 승인 role은 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`다. 운영 창은 `GET /ground-truth-cases?includePending=true`로 첫 승인 대기 사례까지 표시하고, 첫 승인자와 다른 사용자가 2차 승인해야 활성 사례가 된다.

후보 재생성의 제외 사유는 공개되지 않은 문서 버전, 제외/보관 FieldComment, MES 통합 입력 FieldComment, 내용 없는 FieldComment, 역추적 텍스트 없는 작업순서 이력, 누락/보관 보고서 source, 원천이 사라진 보고서 source를 구분해 반환한다. 보고서 source가 `DOCUMENT`를 가리키면 해당 문서와 선택한 버전의 존재 여부를 확인하며, 문서가 `status = DELETED`이거나 `deleted_at`이 설정된 경우도 `report_source_missing_origin`으로 분류해 후보에서 제외한다. 각 제외 사유에는 운영자가 문서 공개, FieldComment 검토/분석, 보고서 source 정리 중 무엇을 해야 하는지 판단할 수 있는 `label`, `operator_action`, `source_type` 안내를 포함한다. `EXCLUDED`, `ARCHIVED` FieldComment는 AI 검색 후보와 보고서 초안 후보 양쪽에서 제외한다.

## 외부 AI 근거 검색과 요약 안전장치

이 절의 질의 생성·조회 라우터, provider 중립 adapter, 원천 권한·민감정보 필터·최소 payload 게이트, 구조·인용·보수적 의미 검증과 차단 감사가 구현되었다. provider별 운영 연동과 재생성 라우터는 아직 구현하지 않는다. generic JSON 네트워크 adapter는 `environment=test`, `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=NETWORK_TEST`, `FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED=true`, HTTPS endpoint, 환경 변수 자격증명을 모두 명시한 제한 시험에서만 생성된다. 외부 호출은 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=true`와 고객·현장별 운영자 승인이 모두 유효할 때만 보고서 작성 role인 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`에게 허용한다. 전역 원천 role이 아닌 사용자는 연결 채널의 활성 멤버십도 필요하다. 허용 목적은 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`뿐이며 자동 의사결정, 작업지시 생성·변경, 승인·공개 자동화, 설비 제어, 안전·품질 판정 요청은 provider 호출 전에 `422 AI_SCOPE_NOT_ALLOWED`로 거부한다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/ai/queries` | 근거 검색·요약 질의 생성. 외부 호출이 꺼져 있으면 `503 AI_EXTERNAL_CALL_DISABLED`, 승인이 없거나 만료·철회·scope 불일치이면 `403 APPROVAL_REVOKED`, 질의 금칙정보는 `422 CONTENT_RESTRICTED` |
| GET | `/api/v1/ai/queries/{query_id}` | 허용된 보고서 작성 role이 질의 상태, 응답 저장 여부/hash, 차단 코드, 적격·제외 근거 snapshot 조회. 현재는 호출자 본인 제한이나 응답 본문·citation 목록 반환은 없음 |

후속 예외로 설계된 `POST /api/v1/ai/queries/{query_id}/regenerations`는 현재 라우터에 등록되어 있지 않다. 보존 기간 안의 질의·프롬프트·근거 snapshot을 사용하는 재생성 계약만 남겨 두며 현재 API로 호출하면 안 된다.

`POST /api/v1/ai/queries` 요청:

```json
{
  "purpose": "EVIDENCE_SUMMARY",
  "query": "프레스 A 금형 교환 중 반복된 문제를 근거와 함께 요약해 주세요.",
  "candidateIds": ["candidate-..."],
  "responseStorageMode": "DO_NOT_STORE"
}
```

`candidateIds`는 선택 사항이며 생략하면 `ai_search_candidates` 정렬 순서의 최대 100건을 검사한다. 서버는 query snapshot 시점에 고객/현장 승인과 허용 source type, 공개 문서와 정확한 공개 버전, `ANALYZED`/`REVIEWED`/`SELECTED` FieldComment, 존재하는 작업순서 이력, 비보관 보고서와 그 실제 원천, 작성자 계정 상태·role, 연결 채널 멤버십을 다시 조회한다. 적격과 제외 후보를 모두 `ai_query_evidence_candidates`에 남기되 제외 후보는 `selected_for_prompt = false`, `sent_externally = false`이고 `SOURCE_FORBIDDEN` 또는 `CONTENT_RESTRICTED` 사유만 기록한다. 원문은 이 감사 row와 일반 로그에 저장하지 않는다.

클라이언트는 provider, model, 시스템 프롬프트를 지정할 수 없다. 서버는 설정의 provider/model과 해당 목적에 대해 최근 승인된 미폐기 `ai_prompt_versions`를 선택한다. provider 경계 DTO는 정제한 `query`, `queryHash`, `purpose`, `promptVersionId`, 표시용 `promptVersion`, 질의 `traceId`, 고정 `outputFormat`과 `sources[]`만 허용한다. 각 source는 안정된 `candidateId`, `sourceType`, `sourceId`, `sourceVersionId`, `traceId`, `traceVersionId`, 원문 `contentHash`, `rank`, 제한 길이 `excerpt`만 가진다. 전체 파일·첨부·사진, 사용자명, 로컬 경로, 내부 URI와 제외 원천은 DTO에 들어가지 않는다. fake와 recording adapter는 이 동일 DTO로 성공·차단·timeout·429/5xx 재시도·불완전 JSON·과대 응답·prompt injection·중복 인용을 결정적으로 재현한다.

기본 필터는 사용자 질의의 주민등록번호·전화번호·이메일을 대체 표식으로 마스킹하고 계정/비밀번호/API key/token, 로컬 경로, 고객 식별자 패턴은 질의 전체를 `CONTENT_RESTRICTED`로 차단한다. 검색 원천은 더 엄격하게 주민등록번호·전화번호·이메일을 포함한 정적 민감 패턴이나 `ai_sensitive_data_policies`의 고객·현장별 금칙어·고객 식별자가 하나라도 검출되면 후보 생성 단계에서 전체 제외한다. 원천 row는 삭제하지 않으며 금지 원문이 후보·근거 snapshot·provider payload에 일부라도 남는 것을 허용하지 않는다.

성공 응답의 `grounded`는 `true`이고, `claims`의 모든 사실 주장에는 하나 이상의 `citations`가 있어야 한다. 서버는 JSON 구조, claim/citation 중복, snapshot ID 존재 여부를 먼저 검사한 뒤 숫자·핵심 토큰 겹침·부정 극성 규칙으로 claim과 최상위 `summary`를 인용 발췌와 보수적으로 대조한다. 이 검증은 provider 모델의 자기평가에 의존하지 않는다. 명백한 수치·극성 모순은 `CLAIM_EVIDENCE_CONFLICT`, 의미 확신 부족은 `CLAIM_GROUNDING_LOW_CONFIDENCE`로 본문 전체를 폐기하며 후자는 `humanReviewRequired = true`인 정상 보류다. 각 citation은 `candidateId`, `sourceType`, `sourceId`, `sourceVersionId`, `traceTable`, `traceId`, `traceVersionId`, `internalSourceUri`를 포함한다. 문서 인용은 `document_id + version_id`, FieldComment 인용은 `comment_id`와 연결된 `document_version_id`(있는 경우), 작업순서 이력 인용은 `change_id`, 보고서 근거 인용은 `report_sources.id`와 그 row의 `source_type + source_id + source_version_id`를 반환한다. `internalSourceUri`는 외부 공개 URL이 아니며, 후속 클라이언트가 사용할 때 원천 권한을 다시 검사해야 한다.

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

검색 결과가 없거나 주장을 뒷받침할 수 없거나 의미 확신이 낮거나 provider 호출 중 승인·원천 상태·사용자 권한이 바뀌면 HTTP 200으로 `status = INSUFFICIENT_EVIDENCE`, `grounded = false`, `summary = null`, `claims = []`, `reason`을 반환한다. provider 응답에 인용이 없거나 후보 snapshot에 없는 ID가 있거나 일부 사실 주장에 인용이 없으면 해당 본문 전체를 폐기하고 `502 CITATION_VALIDATION_FAILED`를 반환한다. 불완전 JSON, 제한 초과, prompt injection 문구도 정제 오류 코드로 전체 폐기한다. timeout, 429, 5xx만 설정된 최대 횟수까지 재시도하며 각 시도를 `ai_call_attempts`로 남긴다. 부분적으로 검증된 문장이나 provider raw body는 답변처럼 노출하지 않는다.

`responseStorageMode = DO_NOT_STORE`에서는 응답 본문을 저장하지 않고 SHA-256 hash만 남긴다. `STORE_90_DAYS`는 응답 본문을 저장한다. 질의는 필터 통과 후 마스킹된 문구만 저장하며 전송 금지 질의는 `[REDACTED]`와 hash만 남긴다. `retention_until` 만료 후 스케줄러는 질의 payload를 비식별화하고 저장 응답 원문을 삭제하며 삭제 감사 row를 남긴다.

## 외부 AI 운영 API

ground-truth 평가 run은 비교 가능한 변경 이력을 위해 선택적 `evaluatorVersion`, `promptVersionId`, `policyVersion`을 metrics snapshot에 보존한다. prompt나 정책 변경 전후 run은 같은 ground-truth case ID를 사용해 비교하며 이전 실패 run을 삭제하거나 덮어쓰지 않는다.

모든 `/api/v1/ai-operations/*` 경로는 `system-admin` 전용이다. 응답은 API key, 질의/응답/근거 원문, provider raw 오류를 포함하지 않는다.

| Method | Path | 용도 |
| --- | --- | --- |
| `GET` | `/api/v1/ai-operations/approvals` | 고객·현장·provider·model·목적·source type·만료가 고정된 승인 조회 |
| `POST` | `/api/v1/ai-operations/approvals` | 범위가 고정된 승인 생성 |
| `POST` | `/api/v1/ai-operations/approvals/{approval_id}/revoke` | 승인 즉시 폐기 |
| `GET` | `/api/v1/ai-operations/provider-reviews` | provider/model별 기술·보안·법무·고객 착수 결정과 필수 체크리스트 조회 |
| `POST` | `/api/v1/ai-operations/provider-reviews` | 불변 review version으로 승인 또는 명시적 대기/거절 상태 기록 |
| `GET` | `/api/v1/ai-operations/prompts` | 불변 프롬프트 버전 조회 |
| `POST` | `/api/v1/ai-operations/prompts` | 새 불변 프롬프트 버전 등록 |
| `POST` | `/api/v1/ai-operations/prompts/{prompt_version_id}/review` | 초안 검토 완료 |
| `POST` | `/api/v1/ai-operations/prompts/{prompt_version_id}/approve` | 검토 프롬프트 승인 |
| `POST` | `/api/v1/ai-operations/prompts/{prompt_version_id}/activate` | 승인 프롬프트 활성화와 같은 목적의 이전 활성 버전 폐기 |
| `POST` | `/api/v1/ai-operations/prompts/{prompt_version_id}/retire` | 프롬프트 폐기 |
| `GET` | `/api/v1/ai-operations/policies` | 전역/현재 현장 운영 정책 조회 |
| `PUT` | `/api/v1/ai-operations/policies` | kill switch, 요청·동시성·timeout·비용·보존·내보내기 정책 저장 |
| `GET` | `/api/v1/ai-operations/audit/queries` | 질의 결과와 근거·인용·호출 감사 검색 |
| `GET` | `/api/v1/ai-operations/audit/events` | 승인·프롬프트·정책 운영 변경 감사 검색 |
| `GET` | `/api/v1/ai-operations/audit/export` | 현장 정책이 허용한 원문 없는 CSV 내보내기 |
| `POST` | `/api/v1/ai-operations/retention/run` | 만료 처리 즉시 실행 |
| `GET` | `/api/v1/ai-operations/retention/audit` | 만료 처리 이력 조회 |

정책의 `maxRequestsPerDay`, `maxConcurrency`, `dailyCostBudgetMicros`가 `0`이면 호출 허용이 아니라 해당 자원을 사용 불가로 해석한다. 비밀은 `FLOWNOTE_AI_{PROVIDER}_API_KEY` 환경 변수 또는 배포 비밀 저장소가 공급하며 정책 응답은 `providerCredentialConfigured` boolean만 반환한다.

검증 테스트 기준:

- 기능 플래그가 꺼진 기본 상태에서 외부 provider client가 한 번도 호출되지 않고 기존 `/api/v1/ai-search/candidates/*`, `/api/v1/ai-search/quality` 테스트가 변경 없이 통과한다.
- 금지 목적, 승인 만료·철회, 권한 없는 채널, 비공개/삭제 문서, 보관 FieldComment와 민감 원천은 provider 호출 전에 차단되고 정제 코드만 감사된다.
- 후보가 0건이면 `INSUFFICIENT_EVIDENCE`이고 조언·추정·작업 지시 문구가 반환되지 않는다.
- 성공 응답의 모든 claim은 질의 시점 후보 snapshot에 있는 citation을 한 개 이상 가지며 원천 row와 version/content hash가 일치한다.
- 인용 누락과 snapshot에 존재하지 않는 후보 ID는 응답 전체를 `CITATION_VALIDATION_FAILED`로 처리한다. 원천 권한·상태와 전송 승인은 snapshot·provider 직전·provider 응답 후에 다시 검사한다.
- fake/recording adapter 테스트는 네 원천 동시 질문, 최소 발췌, candidate/source/version/trace ID·content hash·순위 재현성, 마스킹 전 민감 문자열과 차단 후보의 byte 부재, retry 시도 연결, 인용·의미 일치와 응답 미저장을 검증하며 실제 네트워크를 사용하지 않는다.

## 권한 요약

| 기능 | 허용 role |
| --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` |
| 문서 상태/버전 상태/공개본/삭제 결정 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| FieldComment 등록 | 위 role + `team-member`, `viewer` |
| 접근 로그 조회 | `admin`, `system-admin` |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| 외부 AI 근거 검색·요약(후속 1단계) | `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`. 기능 플래그, 고객·현장별 전송 승인과 원천/채널 권한도 필요 |
| 외부 AI 운영 승인·프롬프트·정책·감사·보존 | `system-admin` 전용 |
| 채널 생성/멤버 관리 | 문서/작업순서 쓰기 role. 단, 채널 조회와 메시지/인수인계 조회는 채널 멤버 또는 `admin`, `system-admin` |

WPF `RolePermissionPolicy`와의 대조:

| WPF 기능 | WPF 허용 role | 서버 대응 정책 |
| --- | --- | --- |
| 문서 등록, 파일 업로드, 작업판 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | `DocumentWriteUser` |
| 문서 상태, 버전 상태, 공개, 삭제 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | `DocumentGovernanceUser` |
| 현장 코멘트 작성 | 기본 role 전체 | `FieldCommentCreateUser` |
| 보고서 버튼 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | `ReportWriteUser` |
| 채널 관리/인수인계 확인 현황 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | 채널 생성은 `DocumentWriteUser`, 조회/읽음/수신확인은 채널 멤버십 또는 `admin`, `system-admin` |
| 파일 감시 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | WPF 로컬 기능 |
| 사용자 관리 | `admin`, `system-admin` | `admin`은 일반 계정, `system-admin`은 system-admin 포함 |
| controlled copy 다운로드 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | 공개 버전 대상 60초 1회성 서버 티켓과 스트리밍 사용 |

정합성 검증 기준:

- FastAPI `app/core/auth.py`는 `DOCUMENT_WRITE_ROLES`, `FIELD_COMMENT_CREATE_ROLES`, `ACCESS_LOG_READ_ROLES`, `REPORT_WRITE_ROLES`, `USER_MANAGEMENT_ROLES`, `CONTROLLED_COPY_DOWNLOAD_ROLES`, `ANDROID_DOCUMENT_VIEW_ROLES`를 권한 표의 기준으로 둔다.
- WPF `RolePermissionPolicy`는 같은 role 집합을 문서 등록, FieldComment 작성, 보고서 작성, 접근 로그 조회, 사용자 관리, controlled copy 다운로드 정책으로 검증한다.
- controlled copy 다운로드는 서버와 WPF 모두 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`로 고정하며 WPF는 로컬 원본 복사 대신 서버 티켓 API를 호출한다.
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
- `FLOWNOTE_CONTROLLED_COPY_MAX_BYTES`
- `FLOWNOTE_CONTROLLED_COPY_TICKET_EXPIRES_SECONDS`
- `FLOWNOTE_ANDROID_VIEW_GRANT_EXPIRES_SECONDS`
- `FLOWNOTE_ANDROID_VIEW_AUTO_CLOSE_SECONDS`
- `FLOWNOTE_ANDROID_VIEW_MAX_BYTES`
- `FLOWNOTE_ANDROID_VIEW_MAX_TEXT_BYTES`
- `FLOWNOTE_ANDROID_VIEW_MAX_PDF_PAGES`
- `FLOWNOTE_SESSION_COOKIE_NAME`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`
- `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED`
- `FLOWNOTE_AI_READINESS_GATE_ENABLED` (기본 `true`)
- `FLOWNOTE_AI_PROVIDER`
- `FLOWNOTE_AI_MODEL`
- `FLOWNOTE_AI_CUSTOMER_SCOPE`
- `FLOWNOTE_AI_SITE_SCOPE`
- `FLOWNOTE_AI_PROVIDER_EXCERPT_MAX_CHARS` (기본 600, 100~4000자)
- `FLOWNOTE_AI_PROVIDER_MAX_SOURCES` (기본 12, 1~100건)
- `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE` (기본 `DISABLED`; `FAKE`, 제한 시험용 `NETWORK_TEST`)
- `FLOWNOTE_AI_FAKE_SCENARIOS` (기본 `SUCCESS`)
- `FLOWNOTE_AI_PROVIDER_ENDPOINT` (`NETWORK_TEST` 전용 HTTPS endpoint)
- `FLOWNOTE_AI_NETWORK_TEST_SCOPE_ENABLED` (기본 `false`)
- `FLOWNOTE_AI_NETWORK_TIMEOUT_SECONDS` (기본 30초, 1~120초)
- `FLOWNOTE_AI_PROVIDER_MAX_ATTEMPTS` (기본 3회, 1~5회)
- `FLOWNOTE_AI_PROVIDER_RESPONSE_MAX_BYTES` (기본 65536바이트, 1024~1048576바이트)
- `FLOWNOTE_AI_RETENTION_SCHEDULER_ENABLED` (기본 `true`)
- `FLOWNOTE_AI_RETENTION_SCHEDULER_INTERVAL_SECONDS` (기본 3600초, 60~86400초)

## AI ground-truth WPF 운영 API

WPF `AI 정답셋` 화면이 사용하는 API와 dataset 운영을 위해 서버가 제공하는 API는 다음과 같다. 응답의 `dataset_version_id`, `snapshot_hash`, 평가 `run_id`는 릴리스 준비도 재현 키다.

| Method | Path | 계약 |
| --- | --- | --- |
| `GET` | `/api/v1/ai-search/ground-truth-cases` | 현재 scope의 독립 2인 승인 사례와 범주/유형, `as_of`, 허용 순위, 포함/제외 원천 snapshot 조회. `includePending=true`는 사례 운영 창에서만 미승인 사례를 포함 |
| `GET` | `/api/v1/ai-search/ground-truth-datasets` | dataset version 목록과 24칸 coverage 집계 조회 |
| `GET` | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}` | 불변 version의 사례·coverage·작성/검토/승인·대체 이력 조회 |
| `POST` | `/api/v1/ai-search/ground-truth-datasets` | 승인 사례를 묶은 새 `DRAFT` version 생성. 대체본은 `replacesDatasetVersionId` 사용 |
| `PUT` | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}/cases` | 작성자만 `DRAFT`의 사례 구성 변경. 이후 상태는 `409`. 서버는 제공하지만 현재 WPF 화면은 직접 호출하지 않음 |
| `POST` | `/api/v1/ai-search/ground-truth-datasets/{dataset_version_id}/transition` | `SUBMIT_REVIEW`, `REVIEW`, `FIRST_APPROVE`, `SECOND_APPROVE`, `RETIRE` 수행 |
| `POST` | `/api/v1/ai-search/evaluations` | `datasetVersionId`로 승인 snapshot 전체 평가. ad-hoc `cases`/`groundTruthCaseIds`와 혼용 금지 |
| `GET` | `/api/v1/ai-search/evaluations` | 저장된 run 목록. `datasetVersionId` 필터 지원 |
| `GET` | `/api/v1/ai-search/evaluations/{run_id}` | 사례별 실패 코드와 기대·실제·제외 원천 trace 조회. `compareToRunId` 비교 지원 |

dataset 상태는 `DRAFT → IN_REVIEW → PENDING_FIRST_APPROVAL → PENDING_SECOND_APPROVAL → APPROVED`다. 작성자, 검토자, 1차 승인자, 2차 승인자는 모두 달라야 하며 서버 상태 전이와 DB 제약이 이를 함께 강제한다. 최종 승인은 총 48건과 8범주×3유형 각 2건을 요구하고 사례 snapshot hash를 다시 확인한다. 대체 version은 같은 고객·현장·DB·라인·준비도 계열과 같은 `datasetKey`의 불변 version만 참조할 수 있다. 대체 version 승인 시 이전 승인본은 삭제·수정하지 않고 `SUPERSEDED`, 명시적 폐기는 `RETIRED`가 된다. dataset 상세·구성 변경·상태 전이는 현재 고객·현장·DB scope 밖의 ID를 `404`로 처리한다.

`GET /api/v1/ai-search/readiness`는 `latest_approved_dataset`, 그 version에 정확히 결합된 `latest_evaluation`, `ai_provider_readiness_status`, `readiness_failures`, `external_ai_calls_blocked`, `non_ai_core_flows_blocked=false`를 반환한다. 승인 dataset 또는 해당 평가가 없으면 `PENDING`, 평가가 존재하지만 임계값 미달이면 `FAIL`, 모든 결합 게이트 통과 시 `PASS`다. `FAIL/PENDING`은 외부 provider 호출만 차단하며 후보 재생성·품질 점검과 문서·FieldComment 등 비AI API는 차단하지 않는다.
## 서버 식별과 무손실 reconciliation

- `GET /api/v1/health/sync-manifest`, `GET /api/v1/sync/manifest`: `server_instance_id`, `server_epoch`, `schema_contract`, `api_contract_min/max`, 현재 `server_cursor`를 반환한다. health 경로는 전송 차단 판단을 위해 인증 없이 읽을 수 있지만 비밀값이나 운영 데이터는 포함하지 않는다.
- `POST /api/v1/sync/server-epoch/increment`: `admin`/`system-admin`만 실행한다. DB 복구·부분 복원 직후 일반 클라이언트를 연결하기 전에 epoch를 1 증가시키며 감사 이력을 남긴다.
- `POST /api/v1/sync/reconciliation-runs`: 관리자 인증과 WPF inventory를 받아 각 항목을 `CONFIRMED`, `ABSENT`, `DIVERGED`로 판정하고 `REBOUND`, `REQUEUE`, `CONFLICT`를 제안한다. 새 `run_id`를 매번 만들며 실패·불일치 항목도 삭제하지 않는다.
- `GET /api/v1/sync/reconciliation-runs/{run_id}`: 저장된 run과 모든 판정·승인 결과를 조회한다.
- `POST /api/v1/sync/reconciliation-runs/{run_id}/apply`: 모든 item에 대한 관리자 승인 조치와 사유가 있어야 종결한다. 동일 적용 요청은 멱등하게 기존 결과를 반환한다.

동일 idempotency key와 payload/file hash의 서버 원천이 있으면 그 server ID/revision을 반환해 재결합한다. 같은 key의 서버 원천이 없으면 기존 key를 유지한 재전송 대상으로 판정하고, 같은 key의 hash가 다르면 자동 덮어쓰기 없이 divergence로 보존한다.
