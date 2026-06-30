# FlowNote API

FastAPI 서버는 `/api/v1` 아래 REST API를 제공한다. 루트 `/`는 서비스 이름과 환경을 반환한다.

## 인증

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | 사용자명/비밀번호 로그인, access token과 refresh token 발급 |
| POST | `/api/v1/auth/refresh` | refresh token 검증 후 같은 세션의 access/refresh token 회전 |
| POST | `/api/v1/auth/logout` | 현재 access token 세션을 `REVOKED`로 변경 |
| GET | `/api/v1/auth/me` | 현재 Bearer token 사용자 정보 조회 |

보호 API는 `Authorization: Bearer {access_token}`을 요구한다. access token은 HMAC 서명 payload이며 서버의 `auth_sessions` 상태와 `access_token_id`까지 검증한다.

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
| GET | `/api/v1/documents/{documentId}` | 문서 상세 |
| GET | `/api/v1/documents/{documentId}/published` | 공개 버전 조회 |
| PUT | `/api/v1/documents/{documentId}/tags` | 문서 태그 교체 |
| PATCH | `/api/v1/documents/{documentId}/status` | 문서 상태 변경 |
| GET | `/api/v1/documents/{documentId}/versions` | 문서 버전 목록 |
| POST | `/api/v1/documents/{documentId}/versions` | 새 파일 버전 등록 |
| PATCH | `/api/v1/documents/{documentId}/versions/{versionId}/status` | 버전 상태 변경 |
| POST | `/api/v1/documents/{documentId}/versions/{versionId}/publish` | 특정 버전을 공개 버전으로 지정 |

문서 생성 시 허용되는 상태는 `WORKING`, `IN_REVIEW`, `ARCHIVED`이다. `PUBLISHED`는 publish 엔드포인트로만 만든다.

## 접근 로그

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/documents/{documentId}/access-logs` | 문서 접근 로그 등록 |
| GET | `/api/v1/documents/{documentId}/access-logs` | 문서 접근 로그 조회 |

`action` 값은 `view_started`, `view_closed`, `download_blocked`, `auto_closed`를 사용한다. 조회는 `admin`, `system-admin`만 가능하다.

## FieldComment

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/field-comments` | FieldComment 원천 기록 등록 |
| GET | `/api/v1/field-comments` | FieldComment 목록 조회 |
| GET | `/api/v1/field-comments/{commentId}` | FieldComment 상세 조회 |
| PATCH | `/api/v1/field-comments/{commentId}` | 상태, 정리 내용, 분석 내용 갱신 |
| POST | `/api/v1/field-comments/{commentId}/attachments` | 첨부 파일 등록 |
| GET | `/api/v1/field-comments/{commentId}/attachments` | 첨부 파일 목록 조회 |
| GET | `/api/v1/documents/{documentId}/field-comments` | 특정 문서의 FieldComment 조회 |

FieldComment는 `documentId`, `structureItemId`, `workRecordId` 중 하나 이상을 참조해야 한다. 현재 구조에서는 문서 참조가 주 사용 경로다.

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
| GET | `/api/v1/work-sequence-boards/{boardId}` | 작업순서 보드 상세 |
| POST | `/api/v1/work-sequence-boards/{boardId}/items` | 항목 추가 |
| PUT | `/api/v1/work-sequence-boards/{boardId}/items/order` | 항목 전체 순서 변경 |
| PATCH | `/api/v1/work-sequence-boards/{boardId}/items/{itemId}/status` | 항목 상태 변경 |
| GET | `/api/v1/work-sequence-boards/{boardId}/history` | 변경 이력 조회 |
| GET | `/api/v1/work-sequence-boards/{boardId}/notification-candidates` | 알림 후보 조회 |
| PATCH | `/api/v1/work-sequence-boards/{boardId}/notification-candidates/{candidateId}` | 알림 후보 상태 변경 |

## 보고서

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/api/v1/reports/drafts` | 수동 보고서 초안 생성 |
| POST | `/api/v1/reports` | 보고서 저장, 선택 시 문서로 저장 |
| GET | `/api/v1/reports` | 보고서 목록 |
| GET | `/api/v1/reports/{reportId}` | 보고서 상세 |

보고서 source 타입은 `FIELD_COMMENT`, `DOCUMENT`, `WORK_SEQUENCE_ITEM`, `WORK_SEQUENCE_HISTORY`, `WORK_RECORD`, `WORK_RECORD_VERSION`을 사용한다.

## 권한 요약

| 기능 | 허용 role |
| --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` |
| FieldComment 등록 | 위 role + `team-member`, `viewer` |
| 접근 로그 조회 | `admin`, `system-admin` |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |

## 설정

- `FLOWNOTE_DATABASE_URL`
- `FLOWNOTE_TEST_DATABASE_URL`
- `FLOWNOTE_STORAGE_ROOT`
- `FLOWNOTE_FIELD_COMMENT_ATTACHMENT_MAX_BYTES`
- `FLOWNOTE_ACCESS_TOKEN_SECRET`
- `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`
- `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`
