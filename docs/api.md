# FlowNote API

FastAPI 서버는 `/api/v1` 아래 REST API를 제공한다. 루트 `/`는 서비스 이름과 환경을 반환한다. `/`, `/api/v1/health`, `/api/v1/health/db`, `GET /api/v1/tags`를 제외한 현재 API는 Bearer token 기반 인증을 요구한다.

## 인증

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 사용자명/비밀번호 로그인, access token과 refresh token 발급 |
| POST | `/api/v1/auth/refresh` | refresh token 검증 후 같은 세션의 access/refresh token 회전 |
| POST | `/api/v1/auth/logout` | 현재 access token 세션을 `REVOKED`로 변경 |
| GET | `/api/v1/auth/me` | 현재 Bearer token 사용자 정보 조회 |

보호 API는 `Authorization: Bearer {access_token}`을 요구한다. access token은 HMAC 서명 payload이며 서버의 `auth_sessions` 상태와 `access_token_id`까지 검증한다.

서버 계정 발급, 잠금, 비밀번호 재설정, role 변경을 수행하는 공개 API는 현재 범위에 추가하지 않는다. 운영 배포 전 기준은 서버 PC의 `app.ops.server_accounts` 운영 스크립트이며, WPF 사용자 관리 화면은 로컬 SQLite 계정만 관리한다. 첫 로그인 후 비밀번호 변경 강제도 현재 응답 payload, 서버 컬럼, WPF 화면에 추가하지 않고 “운영 첫 로그인 전 비밀번호 변경” 절차로 통제한다. `must_change_password` 컬럼, 비밀번호 변경 API, WPF 강제 변경 화면은 후속 범위다.

운영 기준:

- 서버 로그인은 서버 `user_accounts`의 `is_active`와 `status = ACTIVE`를 모두 만족해야 한다.
- 서버 로그인 성공 시 WPF는 서버 응답의 사용자 ID, 표시 이름, role을 현재 세션 기준으로 사용한다.
- 서버가 로그인 요청에 401 또는 403을 반환하면 WPF는 로컬 계정 로그인으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 WPF 로컬 계정 로그인을 사용한다.
- refresh는 같은 `auth_sessions` row에서 access token ID와 refresh token hash를 회전한다. 이전 access token과 이전 refresh token은 거부된다.
- logout은 현재 세션을 `REVOKED`로 바꾸며 이후 같은 access token은 거부된다.
- WPF 서버 동기화 중 인증 만료, 토큰 교체, logout 폐기가 확인되면 `로그인이 만료되었거나 서버 인증이 해제되었습니다. 다시 로그인하세요. 로컬 데이터는 삭제되지 않습니다.` 문구를 표시하고 로컬 데이터와 동기화 큐를 삭제하지 않는다.

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

## 보고서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/reports/drafts` | 수동 보고서 초안 생성 |
| POST | `/api/v1/reports` | 보고서 저장, 선택 시 문서로 저장. `idempotencyKey`를 보내면 같은 키의 재시도는 기존 보고서를 반환 |
| GET | `/api/v1/reports` | 보고서 목록 |
| GET | `/api/v1/reports/{report_id}` | 보고서 상세 |

보고서 source 타입은 `FIELD_COMMENT`, `DOCUMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `WORK_RECORD_VERSION`을 사용한다. WPF 보고서 초안의 FieldComment 후보는 `SELECTED`, `REVIEWED`, `ANALYZED` 순으로 우선 노출하고 `EXCLUDED`, `ARCHIVED` 상태는 후보에서 제외한다.

## AI 검색 근거 후보

AI 검색은 자동 조언이 아니라 “근거가 있는 검색과 요약”을 위한 후보 read model 관리 범위로 둔다. 외부 AI API 호출, 자동 작업지시 변경, 자동 의사결정은 포함하지 않는다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/ai-search/candidates/rebuild` | 현재 DB 기준으로 검색 후보를 재생성하고 후보 수와 제외 사유를 반환 |
| GET | `/api/v1/ai-search/candidates` | 검색 후보 목록 조회. `sourceType`, `sourceId`, `limit`으로 제한 가능 |
| GET | `/api/v1/ai-search/quality` | 후보 수, 원천별 개수, 제외 사유, FieldComment 검토 상태 부족분 조회 |

검색 후보 원천은 `PUBLISHED_DOCUMENT_VERSION`, `FIELD_COMMENT`, `WORK_SEQUENCE_HISTORY`, `REPORT_SOURCE` 네 종류만 허용한다. 각 후보 응답은 `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `parent_type`, `parent_id`를 포함해 원문 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 근거 row로 역추적할 수 있어야 한다.

운영 점검 화면은 `POST /api/v1/ai-search/candidates/rebuild`로 후보를 재생성한 뒤 `GET /api/v1/ai-search/quality`의 `counts_by_source_type`, `excluded_counts_by_reason`, `excluded_reason_guidance`, `field_comment_review_readiness`를 표시한다. 원천별 후보 수는 네 source 타입을 항상 표시하고, FieldComment 검토 준비도는 `ANALYZED`, `REVIEWED`, `SELECTED` 상태 합계가 100건에 부족한 수를 보여준다. 후보 목록에서 운영자는 `trace_table`, `trace_id`, `trace_version_id`로 원문 문서 버전, FieldComment, 작업순서 이력, 보고서 source row로 이동해 근거를 확인한다.

후보 재생성의 제외 사유는 공개되지 않은 문서 버전, 제외/보관 FieldComment, MES 통합 입력 FieldComment, 내용 없는 FieldComment, 역추적 텍스트 없는 작업순서 이력, 누락/보관 보고서 source, 원천이 사라진 보고서 source를 구분해 반환한다. 각 제외 사유에는 운영자가 문서 공개, FieldComment 검토/분석, 보고서 source 정리 중 무엇을 해야 하는지 판단할 수 있는 `label`, `operator_action`, `source_type` 안내를 포함한다. `EXCLUDED`, `ARCHIVED` FieldComment는 AI 검색 후보와 보고서 초안 후보 양쪽에서 제외한다.

## 권한 요약

| 기능 | 허용 role |
| --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` |
| FieldComment 등록 | 위 role + `team-member`, `viewer` |
| 접근 로그 조회 | `admin`, `system-admin` |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |

WPF `RolePermissionPolicy`와의 대조:

| WPF 기능 | WPF 허용 role | 서버 대응 정책 |
| --- | --- | --- |
| 문서 등록, 파일 업로드, 상태 변경, 공개, 작업판 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | `DocumentWriteUser` |
| 현장 코멘트 작성 | 기본 role 전체 | `FieldCommentCreateUser` |
| 보고서 버튼 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | `ReportWriteUser` |
| 파일 감시 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | WPF 로컬 기능 |
| 사용자 관리 | `admin`, `system-admin` | 서버 계정 관리 API는 후속 범위 |
| controlled copy 다운로드 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | 서버 다운로드 API는 후속 범위 |

정합성 검증 기준:

- FastAPI `app/core/auth.py`는 `DOCUMENT_WRITE_ROLES`, `FIELD_COMMENT_CREATE_ROLES`, `ACCESS_LOG_READ_ROLES`, `REPORT_WRITE_ROLES`, `USER_MANAGEMENT_ROLES`, `CONTROLLED_COPY_DOWNLOAD_ROLES`를 권한 표의 기준으로 둔다.
- WPF `RolePermissionPolicy`는 같은 role 집합을 문서 등록, FieldComment 작성, 보고서 작성, 접근 로그 조회, 사용자 관리, controlled copy 다운로드 정책으로 검증한다.
- controlled copy 다운로드는 서버 다운로드 API가 아직 없지만, 서버와 WPF 정책 집합은 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`로 고정한다.
- 서버 로그인 성공 시 WPF 현재 세션의 role은 서버 응답 role을 우선하며, 같은 로그인 ID의 로컬 role과 달라도 화면 권한은 서버 role 기준으로 계산한다.

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
