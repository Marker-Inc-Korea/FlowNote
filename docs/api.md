# FlowNote API 초안

## 0. 현재 구현 API

현재 `services/api/` 코드에서 실제 구현된 FastAPI 엔드포인트는 아래와 같다.

| Method | Path | 현재 응답 |
| --- | --- | --- |
| GET | `/` | 서비스명과 실행 환경 |
| GET | `/api/v1/health` | `{ "status": "ok" }` |
| GET | `/api/v1/health/db` | DB 연결 확인 결과 `{ "status": "ok", "database": "ok" }` |
| POST | `/api/v1/auth/login` | username/password 검증 후 MVP 사용자 정보 반환 |
| POST | `/api/v1/documents` | 문서 메타데이터, 최초 버전, 변경 사유, 로컬 저장 파일 참조 등록 |
| GET | `/api/v1/documents` | 문서 목록과 최신 버전 요약 조회 |
| GET | `/api/v1/documents/{documentId}` | 문서 상세와 최신 버전/파일 참조 조회 |
| GET | `/api/v1/documents/{documentId}/versions` | 문서 버전 목록 조회 |
| POST | `/api/v1/documents/{documentId}/versions` | 새 파일 버전과 변경 사유 등록 |
| POST | `/api/v1/field-notes` | 현장 코멘트 원천 이력 등록 |
| GET | `/api/v1/field-notes` | 현장 코멘트 목록 조회. `documentId`, `status`, `limit` 필터 지원 |
| GET | `/api/v1/field-notes/{noteId}` | 현장 코멘트 상세 조회 |
| PATCH | `/api/v1/field-notes/{noteId}` | 관리자 검토, 정리 문구, 분석 내용 갱신 |
| GET | `/api/v1/documents/{documentId}/field-notes` | 문서별 현장 코멘트 조회 |

문서 등록/버전 등록 API와 현장 코멘트 최소 API는 아직 요청 인증/권한 검사 없이 SQLite와 서버 로컬 `storage/` 저장소 기준으로 동작한다. 로그인 API는 계정 존재, 활성 상태, 비밀번호 일치 여부만 확인하고 아직 JWT를 발급하지 않는 MVP 단계이다. 이하 로그아웃/현재 사용자 API, 현장 단말기 API, 관리자 파일 감시 API, 현장 코멘트 첨부 API, 보고서 API, 작업순서판 API, AI API는 제품 목표를 정리한 서버 API 초안이다. Windows WPF 앱은 `FLOWNOTE_API_BASE_URL`이 설정된 경우 `FlowNoteServerAuthClient`로 서버 로그인 API를 먼저 시도하고, 성공 시 `user_id`, `username`, `role`, `display_name`을 로그인 결과에 보관한다. 서버 URL이 없거나 서버 로그인 호출이 실패하면 기존 로컬 SQLite 로그인 흐름을 유지한다. WPF 앱은 로컬 SQLite FieldNote 저장을 기본 경로로 유지하되, `FlowNoteServerDocumentClient`를 통해 서버 문서 등록/목록/버전 조회와 서버 현장 코멘트 등록 계약을 호출할 수 있다. 문서 보기 창은 로컬 FieldNote 저장 직후에만 서버 현장 코멘트 등록을 후보로 시도하며, 이 시도는 `FLOWNOTE_API_BASE_URL`이 설정된 경우에만 발생한다. 서버 URL이 없거나 전송에 실패해도 로컬 저장 성공은 유지하고 자동 재시도 큐는 아직 만들지 않는다. 현재 스모크 테스트는 `FLOWNOTE_API_BASE_URL`이 설정된 경우 문서 업로드 후 최신 문서 버전에 연결된 현장 코멘트 등록까지 검증한다. 미래 기능은 현재 구현 비교 대상이 아니므로, 아래 항목을 구현 완료 기능으로 해석하지 않는다.

## 1. 공통 원칙

```text
Base Path: /api/v1
Content-Type: application/json
File Upload: multipart/form-data
```

- 외부에는 안정적인 참조 ID를 노출한다.
- 파일 업로드는 `multipart/form-data`를 사용한다.
- 현장 단말기는 기본적으로 현장 공개 상태의 문서를 조회한다.
- 새 문서 버전 등록 시 변경 사유는 필수이다.
- 업로드된 문서가 항상 최신 확정본이라고 가정하지 않고, 작업중/검토중/공개/보관 상태를 구분한다.
- 모든 사용자는 로그인 기반 인증을 거친다.
- 현장 사용자는 문서 열람과 코멘트 등록만 가능하다.
- 문서 파일 다운로드 차단과 문서 뷰어 자동 닫힘은 클라이언트 앱 단계에서 구현한다.
- 현장 사용자 단말기는 파일 감시 API를 사용하지 않는다.
- 관리자만 파일 감시와 업로드 보조 API를 사용할 수 있다.
- Windows WPF 클라이언트 앱은 Python FastAPI 서버와 REST API로 통신한다.
- 앱 로컬 기능은 단말기 모드와 사용자 권한에 따라 제한한다.
- 운영 환경에서는 일반 브라우저 직접 접근보다 승인된 설치형 네이티브 클라이언트 앱 접근을 기본으로 한다.
- 현장 사용자는 탐색기형 기본 검색으로 파일명, 문서명, 태그, 문서 구조, 작업지시 기준의 문서를 찾을 수 있어야 한다.
- 현장 코멘트 입력은 신호등식 기록, 기본 정형 문구, 짧은 메모, 관리자 대리 입력을 우선 지원한다.
- 현장 코멘트와 작업일지성 기록은 사진 첨부를 지원한다.
- 작업순서판은 관리자 입력과 현장 조정 이력을 기준으로 현장 TV 화면에 표시한다.
- 현장 코멘트는 원천 이력이며, 관리자 검토/분석과 보고서 문서로 정제되는 흐름을 가진다.
- 문서 수정자, 열람자, 코멘트 등록자, 실제 전달자 또는 작업자 정보를 추적한다.
- 메타데이터 DB는 SQLite를 우선 사용하고, 필요하면 PostgreSQL로 확장한다.
- 파일은 서버 PC의 로컬 storage 폴더에 저장한다.
- 서비스는 서버 PC 1대와 클라이언트 설치파일 배포를 기본으로 한다.
- FlowNote는 MES/ERP를 대체하지 않고 외부 시스템 연동 대상으로 다룬다.
- AI 검색과 조언은 접근 권한이 있는 데이터만 참조한다.

## 2. 문서 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/documents` | 문서와 최초 버전 등록 |
| GET | `/documents` | 문서 목록 조회 |
| GET | `/documents/{documentId}` | 문서 상세 조회 |
| PATCH | `/documents/{documentId}` | 문서 메타데이터 수정 |
| DELETE | `/documents/{documentId}` | 문서 삭제 상태 처리 |
| GET | `/documents/{documentId}/download` | 관리자 다운로드 API 후보. 클라이언트 앱 단계 |
| GET | `/documents/{documentId}/versions` | 버전 목록 조회 |
| POST | `/documents/{documentId}/versions` | 새 버전 업로드 |
| GET | `/documents/{documentId}/versions/{versionNo}/download` | 관리자 특정 버전 다운로드 API 후보. 클라이언트 앱 단계 |
| GET | `/documents/{documentId}/history` | 문서 이력 조회 |
| GET | `/documents/{documentId}/access-logs` | 접근 로그 조회 |

기본 검색 API:

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/search/documents` | 파일명, 문서명, 태그, 구조, 작업지시 기준 문서 검색 |
| GET | `/search/field-notes` | 현장 코멘트와 사진 기록 검색 |
| GET | `/search/work-sequences` | 작업순서 항목 검색 |

기본 검색은 AI 검색과 분리한다. 1차 MVP에서는 사용자가 권한을 가진 문서와 기록만 목록으로 제공하고, PDF/Office 본문 추출 검색은 후속 인덱싱 단계에서 확장한다.

문서 등록 요청 필드:

```text
multipart/form-data
- file: binary
- title: string
- description: string
- documentType: string
- ownerId: string
- categoryId: string
- versionLabel: string
- changeReason: string
- tags: string[]
- links: object[]
```

현재 구현된 `POST /api/v1/documents`는 `file`, `title`, `documentType`, `changeReason`을 필수로 받고, `description`, `ownerId`, `categoryId`, `versionLabel`, `status`, `createdBy`, `tags`를 선택으로 받는다. `tags`는 multipart form의 반복 필드 또는 쉼표 구분 문자열로 받을 수 있으며 서버는 `tag_definitions`와 `document_tags`에 저장하고 문서 목록/상세 응답에 `tags: string[]`로 반환한다. `links`는 아직 저장하지 않는다. 파일은 `storage/documents/{document_id}/v{version_no}/` 아래에 저장하고, SQLite `file_objects`에는 `storage_key`, 원본 파일명, 확장자, MIME, 파일 계열, 크기, SHA-256 해시를 기록한다.

새 버전 업로드 요청 필드:

```text
multipart/form-data
- file: binary
- versionLabel: string
- changeReason: string
```

현재 구현된 `POST /api/v1/documents/{documentId}/versions`는 `file`과 `changeReason`을 필수로 받는다. 새 버전 등록 시 기존 최신 버전의 `is_latest`를 `false`로 바꾸고 `version_status`를 `SUPERSEDED`로 표시한 뒤, 새 버전을 `is_latest=true`, `version_status=WORKING`으로 저장한다.

## 3. 인증 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/auth/login` | 로그인 |
| POST | `/auth/logout` | 로그아웃 |
| GET | `/auth/me` | 현재 사용자와 역할 조회 |

현재 구현된 `POST /api/v1/auth/login`은 JSON 본문으로 `username`, `password`를 받는다. `username`은 앞뒤 공백을 제거한 뒤 조회한다. 계정 존재, `is_active=true`, `status=ACTIVE`, 비밀번호 일치 여부만 검증하며 JWT는 아직 발급하지 않는다.

요청 예시:

```json
{
  "username": "admin",
  "password": "1234"
}
```

성공 응답은 `user_id`, `username`, `role`, `display_name`으로 제한한다.

```json
{
  "user_id": "user-admin",
  "username": "admin",
  "role": "admin",
  "display_name": "FlowNote Admin"
}
```

잘못된 비밀번호와 없는 계정은 `401`을 반환한다. 비밀번호는 맞지만 `is_active=false`이거나 `status`가 `ACTIVE`가 아니면 `403`을 반환한다.

향후 로그인 응답은 사용자 역할과 단말기 모드에 따라 허용 기능을 포함한다.

## 3.1 작업자/작업그룹 API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/operators` | 작업자 또는 작업그룹 목록 조회 |
| POST | `/operators` | 작업자 또는 작업그룹 등록 |
| PATCH | `/operators/{operatorId}` | 작업자 또는 작업그룹 수정 |

`OperatorProfile`은 로그인 계정과 동일하지 않을 수 있다. 실제 작업자 개인, 작업반, 조장, 관리자 대리 등록자, 외부 시스템 작업자 식별자를 표현한다.

## 4. 현장 단말기 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/terminal/devices` | 단말기 등록 또는 접속 정보 갱신 |
| GET | `/terminal/documents/{documentId}` | 현장 단말기용 공개 문서 조회. 클라이언트 앱 단계 |
| POST | `/terminal/documents/{documentId}/viewer-sessions` | 문서 뷰어 세션 생성. 클라이언트 앱 단계 |
| POST | `/terminal/viewer-sessions/{viewerSessionId}/close` | 문서 뷰어 닫힘 기록. 클라이언트 앱 단계 |
| GET | `/terminal/notifications` | 단말기 알림 목록 조회 |
| POST | `/terminal/notifications/{notificationId}/read` | 알림 읽음 처리 |
| GET | `/terminal/work-sequence-boards/{boardId}` | 현장 TV용 작업순서판 조회 |

현장 단말기 등록 예시:

```json
{
  "deviceId": "terminal-12",
  "deviceName": "Line A Viewer",
  "deviceMode": "viewer",
  "locationCode": "line-a"
}
```

문서 뷰어 세션 응답 예시:

```json
{
  "viewerSessionId": "view_20260520_000001",
  "documentId": "doc_20260520_000001",
  "versionNo": 3,
  "expiresAt": "2026-05-20T10:15:00Z",
  "downloadAllowed": false
}
```

## 5. 관리자 파일 감시 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/admin/file-watchers` | 감시 파일 또는 폴더 등록 |
| GET | `/admin/file-watchers` | 감시 항목 목록 조회 |
| POST | `/admin/file-watchers/{watchedFileId}/changes` | 변경 감지 결과 등록 |
| GET | `/admin/file-change-candidates` | 변경 후보 목록 조회 |
| POST | `/admin/file-change-candidates/{candidateId}/upload-version` | 변경 후보로 새 버전 업로드 |

변경 후보 업로드 요청 필드:

```text
multipart/form-data
- file: binary
- versionLabel: string
- changeReason: string
```

## 6. 클라이언트 로컬 기능 계약

이 섹션은 서버 REST API가 아니라 Windows WPF 클라이언트 내부의 로컬 기능 호출 계약이다. 실제 구현 시 앱 UI와 로컬 기능 모듈 사이의 메시지 형태를 맞춘다.

| Local Action | 방향 | 설명 |
| --- | --- | --- |
| `device.getInfo` | App UI -> Local | 단말기 ID, 모드, 앱 버전 조회 |
| `fileWatch.register` | App UI -> Local | 관리자 단말기 감시 파일 등록 |
| `fileWatch.list` | App UI -> Local | 로컬 감시 항목 조회 |
| `fileWatch.getChanges` | App UI -> Local | 변경 감지 결과 조회 |
| `file.pick` | App UI -> Local | 업로드할 로컬 파일 선택 |
| `notification.show` | App UI -> Local | OS 알림 표시 |
| `viewer.openExternal` | App UI -> Local | 필요 시 외부 뷰어 호출 |

로컬 기능 원칙:

- 현장 사용자 `viewer` 모드에서는 파일 감시 액션을 비활성화한다.
- 앱 로컬 기능은 문서 파일을 자동 동기화하지 않는다.
- 관리자 파일 감시 결과는 서버의 관리자 파일 감시 API로 등록한다.
- 로컬 기능 호출은 감사 로그 대상으로 고려한다.
- 로컬 파일 접근, 파일 감시, 외부 뷰어 호출은 감사 로그 기록 대상이다.

## 7. 권한, 태그, 연결 대상 API

| Method | Path | 설명 |
| --- | --- | --- |
| PUT | `/documents/{documentId}/tags` | 문서 태그 변경 |
| PUT | `/field-notes/{noteId}/tags` | 현장 코멘트 태그 변경 |
| GET | `/tags` | 태그 사전 조회 |
| POST | `/tags` | 태그 등록 |
| PUT | `/documents/{documentId}/links` | 문서 연결 대상 변경 |
| PUT | `/documents/{documentId}/permissions` | 문서 권한 변경 |
| GET | `/documents/{documentId}/notification-targets` | 문서 알림 대상 조회 |

태그는 설비, 품목, 공정, 오류 유형, 라인, 위치, 사용자 정의 유형을 지원한다. 태그는 고객 정의 문서 구조로 표현되지 못한 관계를 보완하기 위한 연결 수단이다.

권한 예시:

```json
[
  {
    "subjectType": "role",
    "subjectId": "field-user",
    "permissions": ["view", "comment"]
  },
  {
    "subjectType": "role",
    "subjectId": "document-admin",
    "permissions": ["view", "download", "comment", "write", "delete", "manage"]
  }
]
```

## 8. 문서 구조 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/document-structures` | 고객 정의 문서 구조 생성 |
| GET | `/document-structures` | 문서 구조 목록 조회 |
| GET | `/document-structures/{structureId}` | 문서 구조 상세 조회 |
| POST | `/document-structures/{structureId}/items` | 구조 항목 생성 |
| PATCH | `/document-structures/{structureId}/items/{itemId}` | 구조 항목 수정 |
| POST | `/document-structures/{structureId}/items/{itemId}/documents` | 구조 항목에 문서 연결 |
| DELETE | `/document-structures/{structureId}/items/{itemId}/documents/{documentId}` | 구조 항목 문서 연결 해제 |

문서 구조 생성 예시:

```json
{
  "structureType": "work_order",
  "title": "WO-20260520-001 작업 문서",
  "sourceType": "manual",
  "workOrderNo": "WO-20260520-001"
}
```

문서 구조는 고객이 정한다. 트리형 구조는 가능한 표현 방식 중 하나이며 기본 강제 구조가 아니다. 현장에서 말하는 BOM 문서 구조도 MES BOM을 차용하는 것이 아니라 현장 문서 정리 용어의 예시로 본다.

초기 작업지시서 구조는 관리자가 직접 입력하는 `manual` 구조를 기본으로 한다. MES/ERP 연동이 추가되면 `externalSystem`, `externalRefId`를 사용해 외부 원본과 매핑한다.

## 9. 현장 코멘트 API

2026-06-25 기준 현재 구현된 최소 범위는 JSON 기반 등록, 목록, 상세, 관리자 검토 갱신, 문서별 조회이다. Windows WPF 클라이언트에는 로컬 `FieldNoteRecord`를 서버 등록 요청으로 변환하는 `ServerFieldNoteCreateRequest`와 서버 응답용 `ServerFieldNoteResponse` 계약이 추가되었다. 사진/첨부 업로드와 문서 구조 항목별 조회는 아래 계약만 남겨둔 후속 구현 범위이다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/field-notes` | 현장 코멘트 등록 |
| GET | `/field-notes` | 현장 코멘트 목록 조회 |
| GET | `/field-notes/{noteId}` | 현장 코멘트 상세 조회 |
| PATCH | `/field-notes/{noteId}` | 관리자 검토와 정리 |
| POST | `/field-notes/{noteId}/attachments` | 현장 코멘트 사진 또는 첨부 등록 |
| GET | `/documents/{documentId}/field-notes` | 문서별 코멘트 조회 |
| GET | `/document-structures/{structureId}/items/{itemId}/field-notes` | 문서 구조 항목별 코멘트 조회 |

직접 입력 예시:

```json
{
  "documentId": "doc_20260520_000001",
  "documentVersionId": "ver_20260520_000003",
  "structureItemId": "item_20260520_000010",
  "noteType": "issue",
  "inputMode": "free_text",
  "rawContent": "도면의 체결 방향 설명이 현장 작업 순서와 다릅니다.",
  "authorId": "user-001",
  "operatorId": "op-line-a-team-1",
  "deviceId": "terminal-12",
  "locationCode": "line-a"
}
```

현재 구현된 `POST /api/v1/field-notes` 요청 본문은 camelCase 필드를 받는다. `documentId`, `structureItemId`, `workRecordId` 중 하나 이상은 필요하다. `documentVersionId`가 들어오면 서버의 기존 `document_versions.version_id`를 참조해야 하며, `documentId`와 함께 보낸 경우 같은 문서의 버전이어야 한다. 서버는 저장 시 `rawContent` 앞뒤 공백을 제거하고, 신규 코멘트 상태를 `NEW`로 시작한다.

서버 응답은 Python API 모델 기준 snake_case 필드이다. Windows 클라이언트의 `ServerFieldNoteResponse`는 이 응답을 `note_id`, `document_id`, `document_version_id`, `raw_content`, `status`, `created_at`, `updated_at` 등으로 역직렬화한다.

```json
{
  "note_id": "note_20260520_000001",
  "document_id": "doc_20260520_000001",
  "document_version_id": "ver_20260520_000003",
  "structure_item_id": "item_20260520_000010",
  "work_record_id": null,
  "note_type": "issue",
  "input_mode": "free_text",
  "signal_level": null,
  "template_id": null,
  "raw_content": "도면의 체결 방향 설명이 현장 작업 순서와 다릅니다.",
  "normalized_content": null,
  "analysis_content": null,
  "author_id": "user-001",
  "reported_by": null,
  "operator_id": "op-line-a-team-1",
  "entry_source": "field_user",
  "device_id": "terminal-12",
  "location_code": "line-a",
  "category": null,
  "priority": null,
  "status": "NEW",
  "reviewed_by": null,
  "analyzed_by": null,
  "created_at": "2026-05-20T10:00:00",
  "updated_at": "2026-05-20T10:00:00",
  "reviewed_at": null,
  "analyzed_at": null
}
```

신호등식 기록 예시:

```json
{
  "documentId": "doc_20260520_000001",
  "structureItemId": "item_20260520_000010",
  "noteType": "work_evaluation",
  "inputMode": "signal",
  "signalLevel": "yellow",
  "rawContent": "주의 필요",
  "authorId": "user-001",
  "operatorId": "op-line-a-team-1",
  "deviceId": "terminal-12"
}
```

관리자 대리 입력 예시:

```json
{
  "documentId": "doc_20260520_000001",
  "noteType": "issue",
  "inputMode": "admin_proxy",
  "rawContent": "작업자가 구두로 체결 순서 설명이 부족하다고 전달함",
  "authorId": "admin-001",
  "reportedBy": "user-001",
  "operatorId": "op-line-a-team-1",
  "locationCode": "line-a"
}
```

관리자 검토/분석 예시:

```json
{
  "status": "ANALYZED",
  "normalizedContent": "체결 순서 설명이 실제 작업 흐름과 불일치함",
  "analysisContent": "동일 공정에서 반복 등록된 문제로, 도면 설명과 작업 표준서의 순서 확인이 필요함",
  "reviewedBy": "admin-001",
  "analyzedBy": "admin-001"
}
```

사진 첨부 등록 요청 필드:

```text
multipart/form-data
- file: binary
- attachmentType: photo
- caption: string
- capturedAt: string
```

## 10. 정형 문구 API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/comment-templates` | 정형 문구 목록 조회 |
| POST | `/comment-templates` | 정형 문구 등록 |
| PATCH | `/comment-templates/{templateId}` | 정형 문구 수정 |

## 11. 보고서 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/reports/drafts` | 보고서 초안 생성 |
| POST | `/reports` | 보고서 저장 |
| GET | `/reports/{reportId}` | 보고서 상세 조회 |
| POST | `/reports/{reportId}/export/document` | 보고서를 문서로 저장 |

보고서 초안 생성 요청 예시:

```json
{
  "reportType": "issue",
  "title": "Line A 체결 순서 문제 분석",
  "workRecordId": "work_20260520_000001",
  "sourceRefs": [
    {
      "sourceType": "field_note",
      "sourceId": "note_20260520_000001"
    },
    {
      "sourceType": "document_version",
      "sourceId": "doc_20260520_000001",
      "sourceVersionId": "ver_3"
    }
  ],
  "useAiDraft": true
}
```

보고서는 원천 코멘트와 작업내역을 정제한 관리자급 문서이다. 최종 승인된 보고서는 `Document`로 저장하고, 원천 데이터는 `ReportSource`로 추적한다.

## 12. 작업내역 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/work-records` | 작업내역 등록 |
| GET | `/work-records/{workRecordId}` | 작업내역 상세 조회 |
| POST | `/work-records/{workRecordId}/versions` | 작업내역 새 버전 등록 |
| GET | `/work-records/{workRecordId}/versions` | 작업내역 버전 목록 조회 |
| PUT | `/work-records/{workRecordId}/participants` | 작업자 또는 작업그룹 연결 |

## 13. 작업순서판 API

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/work-sequence-boards` | 작업순서판 생성 |
| GET | `/work-sequence-boards` | 작업순서판 목록 조회 |
| GET | `/work-sequence-boards/{boardId}` | 작업순서판 상세 조회 |
| POST | `/work-sequence-boards/{boardId}/items` | 작업순서 항목 추가 |
| PATCH | `/work-sequence-boards/{boardId}/items/{sequenceItemId}` | 작업순서 항목 수정 |
| PUT | `/work-sequence-boards/{boardId}/items/order` | 작업순서 재정렬 |
| POST | `/work-sequence-boards/{boardId}/items/{sequenceItemId}/status` | 작업순서 상태 변경 |
| GET | `/work-sequence-boards/{boardId}/history` | 작업순서 변경 이력 조회 |

작업순서 항목 추가 예시:

```json
{
  "workRecordId": "work_20260520_000001",
  "structureItemId": "item_20260520_000010",
  "title": "A 제품 조립",
  "sequenceNo": 10,
  "priority": 1,
  "status": "WAITING",
  "assignedOperatorId": "op-line-a-lead"
}
```

작업순서 재정렬 예시:

```json
{
  "items": [
    {
      "sequenceItemId": "seq_20260520_000002",
      "sequenceNo": 10
    },
    {
      "sequenceItemId": "seq_20260520_000001",
      "sequenceNo": 20
    }
  ],
  "changeReason": "납기 우선순위 변경"
}
```

## 14. AI API

AI API는 1차 체감 기능이 아니라 문서, 작업내역, 현장 코멘트, 보고서가 충분히 쌓인 뒤 활용성을 높이기 위한 후속 API 초안이다. 현재 MVP에서는 파일명, 문서명, 태그, 문서 구조, 작업지시 기준의 기본 검색을 우선하고, AI 검색과 작업 조언은 권한과 인덱싱 구조가 안정화된 뒤 구현한다.

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/ai/search` | 문서, 코멘트, 보고서, 작업내역 자연어 검색 |
| POST | `/ai/work-advice` | 작업 조언 생성 |
| POST | `/ai/risk-preview` | 작업지시 문서 위험 요소 미리보기 |
| POST | `/ai/index/rebuild` | 검색 인덱스 재생성 |

작업 조언 응답은 가능한 경우 근거를 포함한다.

```json
{
  "adviceId": "adv_20260520_000001",
  "summary": "작업 전 체결 방향과 안전 점검 절차를 확인해야 합니다.",
  "risks": [
    "과거 작업에서 도면 설명과 실제 작업 순서가 다르다는 문제가 등록되었습니다."
  ],
  "precautions": [
    "현장 공개 도면과 매뉴얼을 함께 확인하십시오."
  ],
  "sources": [
    {
      "type": "document_version",
      "documentId": "doc_20260520_000001",
      "versionNo": 3
    }
  ]
}
```

## 15. 외부 시스템 연동 API

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/integrations/systems` | 외부 시스템 목록 조회 |
| POST | `/integrations/systems` | 외부 시스템 등록 |
| PATCH | `/integrations/systems/{systemId}` | 외부 시스템 설정 수정 |
| POST | `/integrations/{systemId}/sync/work-orders` | 작업지시 데이터 수신/동기화. 후속 연동 단계 |
| POST | `/integrations/{systemId}/sync/master-data` | 품목, 공정, 설비 등 기준정보 수신/동기화 |
| POST | `/integrations/{systemId}/mappings` | 외부 원본과 FlowNote 엔티티 매핑 |
| GET | `/integrations/{systemId}/mappings` | 매핑 목록 조회 |

연동 예시:

```json
{
  "externalSystem": "MES",
  "externalEntityType": "work_order",
  "externalEntityId": "WO-20260520-001",
  "flowEntityType": "document_structure",
  "flowEntityId": "structure_20260520_000001"
}
```

기존 MES/ERP가 있는 현장은 후속 단계에서 현장별 API 어댑터를 통해 데이터를 받아들인다. 현재 단계의 작업지시는 관리자가 직접 입력하고, 외부 연동이 추가되면 같은 문서 구조와 작업내역 구조에 자동 수신 데이터를 매핑한다.

## 16. 오류 코드

| 코드 | 설명 |
| --- | --- |
| VALIDATION_ERROR | 요청 값 오류 |
| DOCUMENT_NOT_FOUND | 문서 없음 |
| DOCUMENT_STRUCTURE_NOT_FOUND | 문서 구조 없음 |
| DOCUMENT_STRUCTURE_ITEM_NOT_FOUND | 문서 구조 항목 없음 |
| FILE_TOO_LARGE | 파일 크기 제한 초과 |
| FILE_TYPE_NOT_ALLOWED | 허용되지 않은 파일 형식 |
| CHANGE_REASON_REQUIRED | 변경 사유 누락 |
| PERMISSION_DENIED | 권한 없음 |
| LOGIN_REQUIRED | 로그인이 필요함 |
| DOWNLOAD_NOT_ALLOWED | 다운로드 권한 없음. 클라이언트 앱 단계 |
| VIEWER_SESSION_EXPIRED | 뷰어 세션 만료. 클라이언트 앱 단계 |
| FILE_WATCH_NOT_ALLOWED | 파일 감시 권한 없음 |
| WATCHED_FILE_NOT_FOUND | 감시 파일 없음 |
| FILE_CHANGE_CANDIDATE_NOT_FOUND | 파일 변경 후보 없음 |
| FIELD_NOTE_NOT_FOUND | 현장 코멘트 없음 |
| COMMENT_TEMPLATE_NOT_FOUND | 정형 문구 없음 |
| REPORT_NOT_FOUND | 보고서 없음 |
| REPORT_SOURCE_NOT_FOUND | 보고서 원천 연결 없음 |
| WORK_RECORD_NOT_FOUND | 작업내역 없음 |
| OPERATOR_NOT_FOUND | 작업자 또는 작업그룹 없음 |
| WORK_SEQUENCE_BOARD_NOT_FOUND | 작업순서판 없음 |
| WORK_SEQUENCE_ITEM_NOT_FOUND | 작업순서 항목 없음 |
| EXTERNAL_SYSTEM_NOT_FOUND | 외부 시스템 없음 |
| INTEGRATION_MAPPING_NOT_FOUND | 연동 매핑 없음 |
| INTEGRATION_SYNC_FAILED | 외부 시스템 동기화 실패 |
| AI_SEARCH_INDEX_NOT_READY | AI 검색 인덱스 준비 안 됨 |
| LOCAL_ACTION_NOT_ALLOWED | 허용되지 않은 앱 로컬 액션 |
