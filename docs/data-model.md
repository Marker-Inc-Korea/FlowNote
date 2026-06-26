# FlowNote 데이터 모델

## 0. 데이터베이스 기준

### 0.0 현재 코드 기준 로컬 SQLite 모델

현재 실제 코드에서 사용하는 SQLite 모델은 Windows WPF 앱의 로컬 프로토타입 모델이다. DB 파일은 개발 실행 기준 `apps/windows/src/FlowNote.Windows.App/Data/flownote.local.sqlite`를 우선 사용하고, 배포 실행처럼 소스 프로젝트를 찾을 수 없는 경우 앱 실행 폴더의 `Data/flownote.local.sqlite`를 사용한다.

현재 구현 테이블은 다음과 같다.

| 테이블 | 현재 역할 |
| --- | --- |
| `user_accounts` | 로그인 계정. 기본 `admin / 1234`와 테스트 계정 `jobhead / 반장 / 1234`를 저장 |
| `document_folders` | 루트, 기본 폴더, 문서 분류 폴더, 날짜 하위 폴더를 저장 |
| `documents` | 문서 메타데이터, 로컬 파일 상대 경로, 상태, 최신 버전, 최신 코멘트 요약을 저장 |
| `document_versions` | 원본 등록 버전과 파일 개정 버전을 저장. 기존 코멘트 버전은 호환용으로 남아 있으나 신규 WPF 코멘트 저장 기본 경로는 아님 |
| `field_notes` | WPF 오프라인 현장 코멘트 최소 원천 이력. 문서 ID, 현재 문서 버전 번호, 입력 방식, 원문, 작성자, 동기화 상태 후보를 저장 |
| `notifications` | 새 현장 코멘트 또는 기존 코멘트 버전 생성 시 문서 작성자/관련 작성자 대상 알림을 저장 |

현재 앱은 문서 등록 시 상태를 `WORKING`으로 저장한다. WPF 문서 보기 화면에서 새로 남기는 코멘트는 `field_notes`에 저장하고, `document_versions`는 문서 파일 개정 이력으로 유지한다. 기존 DB에 `document_versions.comment`로 누적된 코멘트는 앱 초기화 시 `field_notes`로 백필한다. WPF 서버 API 클라이언트는 로컬 FieldNote를 서버 `field_notes` 등록 요청으로 변환할 수 있지만, 로컬 DB의 `document_version_no`는 서버 등록 시 직접 전송하지 않고 서버의 `document_versions.version_id`가 확인된 경우 `documentVersionId`로 전달한다. 문서 보기 창은 로컬 FieldNote 저장 직후에만 서버 등록을 후보로 시도하고, 서버 URL이 없거나 전송이 실패해도 로컬 저장을 성공으로 유지한다. 현재 WPF 로컬 앱은 `synced_at` 기반 자동 재시도 큐나 서버 note ID 매핑을 아직 구현하지 않는다. `IN_REVIEW`, `PUBLISHED`, `ARCHIVED` 같은 상태 전환, 역할 테이블, 권한 테이블, 접근 로그, 태그, 작업내역, 보고서, AI 로그, 서버 저장소용 `FileObject`는 아직 WPF 로컬 앱 코드에 구현되어 있지 않다. 아래 데이터 모델은 제품 목표와 서버 확장 초안이며 현재 코드 구현 완료를 뜻하지 않는다.

### 0.0.1 FastAPI 서버 SQLite 초기 모델

2026-06-24 기준 FastAPI 서버에는 SQLite 연결과 MVP 초기 테이블 생성 기준이 추가되었다. 서버 DB는 `services/api/app/db/models.py`의 SQLAlchemy 모델을 기준으로 하고, 앱 시작 시 `schema_migrations`에 `0001_initial_mvp_schema`를 기록한다. 문서 등록 API는 `documents`, `document_versions`, `file_objects`를 함께 사용해 문서 메타데이터, 파일 저장 참조, 버전 번호, 변경 사유를 로컬에 저장한다.

2026-06-25 기준 서버 로그인 API는 `user_accounts`의 `username`, `password_hash`, `role`, `is_active`, `status`를 사용한다. 서버 DB 초기화 시 개발용 기본 관리자 계정 `admin / 1234`가 없으면 생성한다. 이 기본 계정은 로컬 개발과 MVP 검증용 기준이며, 운영 배포에서는 별도 초기 비밀번호 정책으로 교체해야 한다. 같은 기준일에 Windows WPF 서버 API 클라이언트는 서버 문서 등록/목록/버전 조회뿐 아니라 문서 버전에 연결된 서버 FieldNote 등록 응답까지 받을 수 있다.

기본 개발 DB 경로는 `services/api/data/flownote.sqlite3`, 테스트 DB 경로는 `services/api/data/flownote.test.sqlite3`이다. 테스트 DB와 검증 기록은 로컬 산출물로 보존하되 커밋 대상은 아니다. 문서 등록 통합 테스트 샘플과 로그는 `services/api/data/test-artifacts/document-registration-2026-06-24/` 아래에 보존하고, 업로드 저장 파일은 `services/api/storage/document-registration-tests/` 아래에 보존한다.

현재 서버 초기 스키마 테이블은 다음과 같다.

| 테이블 | 현재 역할 |
| --- | --- |
| `schema_migrations` | 서버 DB 스키마 적용 버전 기록 |
| `user_accounts`, `roles`, `user_roles` | 로그인 계정과 역할 연결의 초기 기준 |
| `operator_profiles` | 실제 작업자, 작업그룹, 대리 등록 주체 추적 |
| `file_objects` | 서버 로컬 `storage/` 파일 참조 |
| `documents`, `document_versions` | 문서 메타데이터, 버전, 변경 사유, 공개/최신 구분 |
| `tag_definitions`, `document_tags` | 설비, 품목, 공정, 오류 유형 등 태그 연결 |
| `terminal_devices` | 현장/관리자 단말기 등록 기준 |
| `field_notes`, `field_note_attachments` | 현장 코멘트 원천 이력과 사진/첨부 연결 |
| `comment_templates` | 신호등식/정형 문구 입력 보조 |
| `work_records`, `work_record_versions` | 작업내역과 버전의 초기 기준 |
| `reports`, `report_sources` | 관리자 보고서와 원천 데이터 추적 |
| `document_access_logs` | 문서 열람, 다운로드 차단, 뷰어 닫힘 등 감사 로그 기반 |

FlowNote의 메타데이터 DB는 SQLite를 우선 사용한다. 현장 규모나 동시성이 커지면 PostgreSQL로 확장한다.

파일 바이너리는 DB에 직접 저장하지 않고 서버 PC의 로컬 `storage/` 폴더에 저장한다. 현재 문서 업로드 저장 키는 `documents/{document_id}/v{version_no}/{uuid}_{safe_filename}` 형식을 사용한다. SQLite에는 문서 메타데이터, 파일 참조 정보, 버전, 변경 사유, 권한, 이력, 단말기, 현장 코멘트, 작업내역, AI 조언 로그를 저장한다.

FlowNote는 MES/ERP를 대체하지 않는다. 외부 시스템이 있는 경우 원본 업무 데이터는 해당 시스템에 두고, FlowNote는 외부 참조 ID와 매핑 정보를 저장해 문서, 현장 코멘트, 작업내역, 보고서와 연결한다.

## 0.1 회원과 권한 모델

### UserAccount

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| user_id | 외부 참조용 사용자 ID |
| username | 로그인 API에서 조회하는 사용자명. 서버 MVP에서는 고유값 |
| login_id | 로그인 ID |
| display_name | 표시명 |
| role | 서버 MVP 로그인 응답에 포함하는 단일 역할. 현재 코드 값은 admin, manager, viewer |
| password_hash | 비밀번호 해시 |
| is_active | 로그인 허용 여부 |
| status | ACTIVE, LOCKED, DISABLED |
| created_at | 생성일 |
| updated_at | 수정일 |

### Role

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| role_id | 외부 참조용 역할 ID |
| role_name | 역할명 |
| description | 설명 |

기본 역할:

- `field-user`: 현장 사용자
- `document-admin`: 문서 관리자
- `system-admin`: 시스템 관리자

### UserRole

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| user_id | 사용자 ID |
| role_id | 역할 ID |
| created_at | 생성일 |

### OperatorProfile

현장 작업자, 작업반, 조장, 관리자 대리 등록자처럼 실제 현장 이력에 남겨야 하는 작업 주체를 관리한다. 모든 현장에서 작업자 개인을 1명씩 식별할 수 있는 것은 아니므로 개인, 그룹, 역할, 대리 등록자를 모두 표현할 수 있게 한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| operator_id | 외부 참조용 작업자/작업그룹 ID |
| operator_type | individual, group, lead, proxy_admin, external 등 |
| user_id | 로그인 계정과 연결되는 경우 사용자 ID |
| display_name | 표시명 |
| line_code | 라인 코드 |
| process_code | 공정 코드 |
| equipment_code | 설비 코드 |
| status | ACTIVE, INACTIVE |
| created_at | 생성일 |
| updated_at | 수정일 |

문서 수정, 문서 열람, 현장 코멘트, 작업내역은 가능한 경우 `UserAccount`와 `OperatorProfile`을 함께 남긴다. 사용자가 직접 입력하지 않고 관리자가 대리 등록한 경우에도 실제 전달자 또는 작업그룹을 추적할 수 있어야 한다.

### LoginSession

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| session_id | 외부 참조용 세션 ID |
| user_id | 사용자 ID |
| device_id | 단말기 ID |
| issued_at | 발급일 |
| expires_at | 만료일 |
| revoked_at | 폐기일 |

## 1. 문서 모델

### Document

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 외부 참조용 문서 ID |
| title | 문서명 |
| description | 설명 |
| document_type | technical_document, drawing, manual, work_instruction 등 |
| owner_id | 소유자 |
| category_id | 분류 |
| status | WORKING, IN_REVIEW, PUBLISHED, ARCHIVED, DELETED |
| latest_version_id | 가장 최근 등록 버전 ID |
| published_version_id | 현장 공개 버전 ID |
| created_at | 생성일 |
| updated_at | 수정일 |
| deleted_at | 삭제 처리일 |

### FileObject

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| storage_type | local 우선. 후속 확장 시 nas, object 등 |
| storage_key | 저장소 경로 또는 object key |
| original_filename | 원본 파일명 |
| extension | 확장자 |
| mime_type | MIME 타입 |
| file_family | hwp, word, powerpoint, excel, pdf, dwg 등 |
| size_bytes | 파일 크기 |
| hash_sha256 | 무결성 검증용 해시 |
| created_at | 생성일 |

### DocumentVersion

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| file_object_id | 파일 객체 ID |
| version_no | 버전 번호 |
| version_label | 표시용 버전명 |
| change_reason | 변경 사유 |
| version_status | WORKING, IN_REVIEW, APPROVED, PUBLISHED, SUPERSEDED, ARCHIVED |
| is_latest | 가장 최근 등록 버전 여부 |
| is_published | 현장 공개 버전 여부 |
| published_at | 현장 공개일 |
| created_by | 등록자 |
| created_at | 등록일 |

`change_reason`은 새 버전 등록 시 필수이다. 업로드된 문서가 항상 최신 확정본이라고 가정하지 않는다. 가장 최근 등록 버전은 `latest_version_id`, 현장 공개 대상 버전은 `published_version_id`로 구분한다.

## 2. 문서 보조 모델

### DocumentTag

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| tag_id | 태그 ID |
| created_at | 생성일 |

### TagDefinition

설비, 품목, 공정, 오류 유형 등 공통 태그 사전을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| tag_id | 외부 참조용 태그 ID |
| tag_type | equipment, item, process, error_type, line, location, custom 등 |
| code | 태그 코드 |
| name | 표시명 |
| parent_tag_id | 상위 태그 ID |
| external_system | 외부 시스템 코드 |
| external_ref_id | 외부 시스템 참조 ID |
| is_active | 사용 여부 |
| created_at | 생성일 |

### FieldNoteTag

현장 코멘트와 태그의 연결을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| note_id | 현장 코멘트 ID |
| tag_id | 태그 ID |
| created_at | 생성일 |

문서 구조에 흡수되지 못한 관계는 태그로 보완한다. 같은 설비, 품목, 공정, 오류 유형 태그를 공유하는 문서와 현장 코멘트는 AI 검색과 보고서 생성에서 함께 참조할 수 있다.

### DocumentLink

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| system_code | 외부 시스템 코드 |
| entity_type | line, equipment, process, product 등 |
| entity_id | 연결 대상 ID |
| created_at | 생성일 |

`DocumentLink`는 외부 시스템의 단순 대상 연결에 사용한다. 고객이 정한 문서 정리 구조가 필요한 경우에는 `DocumentStructure` 모델을 사용한다.

## 2.1 외부 시스템 연동 모델

### ExternalSystem

MES, ERP, 기타 업무 시스템의 연결 정보를 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| system_id | 외부 참조용 시스템 ID |
| system_code | mes, erp, custom 등 |
| name | 시스템명 |
| integration_type | api, database, file |
| base_url | API 기준 주소 |
| is_active | 사용 여부 |
| created_at | 생성일 |
| updated_at | 수정일 |

### IntegrationMapping

외부 시스템의 원본 데이터와 FlowNote 내부 데이터를 연결한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| mapping_id | 외부 참조용 매핑 ID |
| system_id | 외부 시스템 ID |
| external_entity_type | work_order, item, process, equipment, production_result 등 |
| external_entity_id | 외부 시스템 원본 ID |
| flow_entity_type | document_structure, document_structure_item, work_record, field_note, document 등 |
| flow_entity_id | FlowNote 내부 참조 ID |
| sync_status | PENDING, SYNCED, FAILED, DISABLED |
| last_synced_at | 마지막 동기화 일시 |
| created_at | 생성일 |

FlowNote는 외부 시스템의 원본 데이터를 임의로 대체하지 않는다. 매핑은 AI 검색과 조언에서 정형 생산 데이터와 현장지식 데이터를 함께 찾기 위한 연결 정보이다.

### DocumentStructure

고객이 정한 문서 정리 구조의 루트를 관리한다. 트리 구조는 가능한 표현 방식 중 하나일 뿐 기본 강제 구조가 아니다. 현장에서 말하는 BOM 문서 구조는 MES BOM이 아니라 문서를 계층적으로 정리해 부르는 현장 용어의 예시이다. 초기 작업지시서 구조는 MES 연동이 아니라 관리자가 직접 입력하는 `manual` 출처를 기본으로 한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| structure_id | 외부 참조용 구조 ID |
| structure_type | custom, work_order, project, folder, hierarchy 등 |
| title | 구조명 |
| source_type | manual, external |
| external_system | MES/ERP 등 외부 시스템 코드. 외부 연동 시 사용 |
| external_ref_id | 외부 프로젝트 또는 작업지시서 ID. 외부 연동 시 사용 |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### DocumentStructureItem

문서 구조의 항목을 관리한다. 트리 노드처럼 사용할 수도 있고, 고객이 쓰는 분류 항목처럼 사용할 수도 있다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| item_id | 외부 참조용 항목 ID |
| structure_id | 구조 ID |
| parent_item_id | 부모 항목 ID. 트리형 구조에서 사용 |
| item_type | folder, group, work_order, process, item, custom 등 |
| title | 항목명 |
| sort_order | 표시 순서 |
| external_ref_id | 외부 참조 ID. 외부 연동 시 사용 |
| created_at | 생성일 |
| updated_at | 수정일 |

### DocumentStructureItemDocument

문서 구조 항목과 문서의 연결을 관리한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| item_id | 구조 항목 ID |
| document_id | 문서 ID |
| document_version_id | 특정 버전을 고정 연결할 경우 사용 |
| link_type | required, reference, work_instruction, drawing 등 |
| created_at | 생성일 |

### DocumentPermission

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| subject_type | user, group, role, public |
| subject_id | 권한 주체 ID |
| permission | view, download, comment, write, delete, manage |
| created_at | 생성일 |

### DocumentHistory

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| document_version_id | 관련 버전 ID |
| event_type | 이벤트 유형 |
| before_value | 변경 전 값 |
| after_value | 변경 후 값 |
| change_reason | 변경 사유 |
| actor_id | 수행자 |
| created_at | 생성일 |

### DocumentAccessLog

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| document_id | 문서 ID |
| document_version_id | 접근 버전 ID |
| action | view, viewer_auto_closed, download, denied 등 |
| actor_id | 접근자 |
| device_id | 단말기 ID |
| client_ip | 클라이언트 IP |
| user_agent | User-Agent |
| created_at | 생성일 |

## 3. 단말기와 알림

### TerminalDevice

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| device_id | 외부 참조용 단말기 ID |
| device_name | 단말기명 |
| device_mode | viewer, admin_support |
| location_code | 위치 또는 현장 코드 |
| group_id | 단말기 그룹 ID |
| status | ACTIVE, INACTIVE |
| last_seen_at | 마지막 접속일 |
| created_at | 생성일 |

### Notification

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| notification_id | 외부 참조용 알림 ID |
| event_type | DOCUMENT_VERSION_PUBLISHED 등 |
| title | 알림 제목 |
| message | 알림 내용 |
| document_id | 관련 문서 ID |
| document_version_id | 관련 버전 ID |
| target_type | user, group, role, device, device_group |
| target_id | 대상 ID |
| status | PENDING, SENT, READ, FAILED |
| created_at | 생성일 |
| sent_at | 발송일 |
| read_at | 읽은 일시 |

알림 이벤트는 문서 공개, 새 버전 등록, 현장 코멘트 등록, 사진 기록 등록, 작업순서 변경, 작업순서 상태 변경을 포함한다.

### ViewerSession

문서 뷰어 열람 세션과 자동 닫힘 시간을 관리한다. 이 모델은 Windows WPF 클라이언트 앱과 Python FastAPI 서버의 감사 로그 연동에서 사용한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| viewer_session_id | 외부 참조용 뷰어 세션 ID |
| document_id | 문서 ID |
| document_version_id | 문서 버전 ID |
| user_id | 사용자 ID |
| device_id | 단말기 ID |
| opened_at | 열람 시작일 |
| expires_at | 자동 닫힘 예정일 |
| closed_at | 실제 닫힘 일시 |
| close_reason | user_closed, timeout, permission_revoked |

## 4. 관리자 파일 감시

### WatchedFile

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| watched_file_id | 외부 참조용 감시 항목 ID |
| device_id | 관리자 단말기 ID |
| document_id | 연결 문서 ID |
| local_path | 감시 대상 경로 |
| watch_type | file, folder |
| last_modified_at | 마지막 수정일 |
| last_size_bytes | 마지막 파일 크기 |
| last_hash_sha256 | 마지막 해시 |
| status | ACTIVE, PAUSED, REMOVED |
| created_by | 등록자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### FileChangeCandidate

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| candidate_id | 외부 참조용 후보 ID |
| watched_file_id | 감시 항목 ID |
| document_id | 연결 문서 ID |
| detected_modified_at | 감지 수정일 |
| detected_size_bytes | 감지 파일 크기 |
| detected_hash_sha256 | 감지 해시 |
| status | DETECTED, IGNORED, UPLOADED |
| uploaded_version_id | 업로드된 버전 ID |
| detected_at | 감지일 |
| resolved_at | 처리일 |

## 5. 현장 코멘트와 보고서

### FieldNote

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| note_id | 외부 참조용 문구 ID |
| document_id | 연결 문서 ID |
| document_version_id | 연결 버전 ID |
| structure_item_id | 연결 문서 구조 항목 ID |
| work_record_id | 연결 작업내역 ID |
| note_type | experience, work_evaluation, issue |
| input_mode | signal, free_text, template, template_with_text, admin_proxy, mes_integration |
| signal_level | green, yellow, red 등 단순 상태 값 |
| template_id | 선택한 정형 문구 ID |
| raw_content | 현장 사용자 입력 원문 |
| normalized_content | 관리자 정리 문구 |
| analysis_content | 관리자 분석 내용 |
| author_id | 입력자 |
| reported_by | 실제 현장 전달자 또는 작업자 |
| operator_id | 작업자 또는 작업그룹 ID |
| entry_source | field_user, admin_proxy, mes, system |
| device_id | 단말기 ID |
| location_code | 위치 또는 현장 코드 |
| category | 분류 |
| priority | 중요도 |
| status | NEW, NEEDS_REVIEW, ANALYZED, REVIEWED, SELECTED, EXCLUDED, ARCHIVED |
| reviewed_by | 검토자 |
| analyzed_by | 분석자 |
| created_at | 등록일 |
| updated_at | 수정일 |
| reviewed_at | 검토일 |
| analyzed_at | 분석일 |

`FieldNote`는 최소 하나의 연결 대상이 있어야 한다. 현재 서버 API는 `document_id`, `structure_item_id`, `work_record_id` 중 하나 이상을 요구한다. `document_version_id`가 있으면 서버 `document_versions.version_id`와 일치해야 하며, `document_id`와 함께 들어온 경우 같은 문서의 버전이어야 한다. 1차 MVP에서는 문서 또는 문서 버전 연결을 우선 사용하고, 문서 구조 항목과 작업내역 연결은 후속 단계에서 확장한다.

초기 현장 입력은 많은 텍스트를 요구하지 않는다. `signal`은 정상, 주의, 문제 같은 신호등식 기록이고, `admin_proxy`는 현장 사용자가 말로 전달한 내용을 관리자가 대신 등록하는 방식이다. `mes_integration`은 MES나 자동화 시스템 연동 이후 사용한다.

`raw_content`는 원천 이력, `normalized_content`는 관리자 정리 문구, `analysis_content`는 관리자급 사용자의 판단과 분석이다. 코멘트만 쌓아서는 실제 활용이 어려우므로, 보고서 작성 시 어떤 원천 코멘트가 어떤 분석과 결론으로 이어졌는지 추적해야 한다.

### FieldNoteAttachment

현장 코멘트 또는 일일 작업일지성 기록에 첨부된 사진과 파일을 관리한다. 사진은 보고서 자동화의 원천 데이터가 될 수 있지만, 1차 MVP에서는 첨부, 열람, 이력 추적을 우선한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| attachment_id | 외부 참조용 첨부 ID |
| note_id | 현장 코멘트 ID |
| file_object_id | 첨부 파일 객체 ID |
| attachment_type | photo, document, other |
| caption | 현장 메모 또는 사진 설명 |
| captured_at | 촬영 시각. 알 수 있는 경우 |
| created_by | 등록자 |
| created_at | 등록일 |

### CommentTemplate

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| template_id | 외부 참조용 템플릿 ID |
| title | 표시 문구 |
| content | 기본 등록 문구 |
| note_type | 문구 유형 |
| document_type | 적용 문서 유형 |
| category | 분류 |
| location_code | 적용 위치 |
| is_active | 사용 여부 |
| sort_order | 표시 순서 |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### Report

현장 코멘트, 작업내역, 관련 문서를 기반으로 관리자가 정리한 보고서를 관리한다. AI는 보고서 초안을 도울 수 있지만, 최종 보고서는 관리자급 사용자의 검토를 거친 문서로 남긴다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| report_id | 외부 참조용 보고서 ID |
| report_type | production, issue, improvement, inspection, custom 등 |
| title | 보고서 제목 |
| summary | 요약 |
| analysis_content | 관리자 분석 내용 |
| conclusion | 결론 |
| action_plan | 조치 계획 |
| work_record_id | 관련 작업내역 ID |
| structure_item_id | 관련 문서 구조 항목 ID |
| period_start | 보고 대상 시작일 |
| period_end | 보고 대상 종료일 |
| status | DRAFT, AI_DRAFTED, REVIEWED, APPROVED, ARCHIVED |
| ai_draft_used | AI 초안 사용 여부 |
| generated_document_id | 최종 문서로 저장된 Document ID |
| created_by | 작성자 |
| reviewed_by | 검토자 |
| approved_by | 승인자 |
| created_at | 생성일 |
| reviewed_at | 검토일 |
| approved_at | 승인일 |

### ReportSource

보고서가 어떤 원천 데이터에서 만들어졌는지 추적한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| report_id | 보고서 ID |
| source_type | field_note, work_record_version, document_version, external_ref 등 |
| source_id | 원천 데이터 ID |
| source_version_id | 원천 버전 ID |
| relation_type | evidence, issue, action, reference 등 |
| created_at | 생성일 |

최종 보고서는 `Document`로 저장하고 원천 코멘트, 작업내역, 관련 문서는 `ReportSource`로 추적한다. 보고서만 있으면 상세 이력을 알기 어렵고, 원천 이력만 있으면 의사결정에 쓰기 어렵기 때문에 두 계층을 모두 유지한다.

## 6. 작업내역과 AI

### WorkRecord

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 외부 참조용 작업내역 ID |
| work_order_no | 작업지시 번호 |
| title | 작업 제목 |
| work_instruction_document_id | 작업지시 문서 ID |
| source_type | manual, external |
| external_system | MES/ERP 등 외부 시스템 코드. 외부 연동 시 사용 |
| external_ref_id | 외부 작업지시 ID. 외부 연동 시 사용 |
| status | DRAFT, ACTIVE, COMPLETED, ARCHIVED |
| latest_version_id | 가장 최근 등록 작업내역 버전 ID |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### WorkRecordVersion

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| version_no | 버전 번호 |
| summary | 작업 요약 |
| result_note | 작업 결과 |
| issue_note | 발생 문제 |
| action_note | 조치 내용 |
| change_reason | 변경 사유 |
| created_by | 등록자 |
| created_at | 등록일 |

### WorkRecordDocument

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| document_id | 관련 문서 ID |
| document_version_id | 관련 문서 버전 ID |
| relation_type | instruction, reference, evidence |
| created_at | 생성일 |

### WorkRecordParticipant

작업내역에 참여하거나 보고된 작업 주체를 연결한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| work_record_id | 작업내역 ID |
| operator_id | 작업자 또는 작업그룹 ID |
| user_id | 로그인 사용자 ID. 있는 경우 |
| role_type | worker, lead, supervisor, reporter, reviewer 등 |
| created_at | 생성일 |

### WorkSequenceBoard

사무실, 관리자, 반장, 조장이 현장 처리 순서를 공유하기 위한 작업순서판을 관리한다. 작업순서판은 MES 작업지시를 대체하지 않고, 현재 현장에서 어떤 순서로 처리할지 보여주는 운영 화면이다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| board_id | 외부 참조용 작업순서판 ID |
| title | 작업순서판명 |
| location_code | 라인, 현장, 구역 코드 |
| process_code | 공정 코드 |
| status | ACTIVE, PAUSED, ARCHIVED |
| created_by | 생성자 |
| created_at | 생성일 |
| updated_at | 수정일 |

### WorkSequenceItem

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| sequence_item_id | 외부 참조용 작업순서 항목 ID |
| board_id | 작업순서판 ID |
| work_record_id | 연결 작업내역 ID |
| structure_item_id | 연결 문서 구조 항목 ID |
| external_ref_id | MES/ERP 작업지시 등 외부 참조 ID |
| title | 표시 제목 |
| sequence_no | 표시 순서 |
| priority | 우선순위 |
| status | WAITING, IN_PROGRESS, HOLD, COMPLETED, CANCELED |
| assigned_operator_id | 작업반, 조장, 담당자 |
| planned_start_at | 계획 시작 시각 |
| planned_end_at | 계획 종료 시각 |
| updated_by | 마지막 변경자 |
| updated_at | 수정일 |

### WorkSequenceHistory

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| sequence_item_id | 작업순서 항목 ID |
| event_type | reordered, status_changed, assigned, memo_updated 등 |
| before_value | 변경 전 값 |
| after_value | 변경 후 값 |
| change_reason | 변경 사유 또는 메모 |
| actor_id | 수행자 |
| created_at | 생성일 |

### SearchIndexItem

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| source_type | document_version, field_note, report, work_record_version |
| source_id | 원천 데이터 ID |
| source_version_id | 원천 버전 ID |
| title | 검색 표시 제목 |
| content_text | 검색 대상 텍스트 |
| permission_scope | 검색 권한 범위 |
| indexed_at | 인덱싱 일시 |

### AiAdviceLog

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| advice_id | 외부 참조용 조언 ID |
| request_type | search, work_advice, risk_preview |
| query | 사용자 질의 또는 분석 요청 |
| work_record_id | 관련 작업내역 ID |
| document_id | 관련 문서 ID |
| response_summary | AI 응답 요약 |
| source_refs | 근거 참조 목록 |
| created_by | 요청자 |
| created_at | 생성일 |

### ClientLocalActionLog

Windows WPF 클라이언트 앱의 로컬 기능 호출 중 감사가 필요한 요청을 기록한다.

| 필드 | 설명 |
| --- | --- |
| id | 내부 식별자 |
| local_action_id | 외부 참조용 로컬 기능 감사 ID |
| device_id | 단말기 ID |
| user_id | 사용자 ID |
| action | 로컬 기능 액션명 |
| request_summary | 요청 요약 |
| result | success, denied, failed |
| created_at | 생성일 |

## 7. 식별자 원칙

- 내부 DB 식별자와 외부 참조용 ID를 분리한다.
- 외부에는 `user_id`, `operator_id`, `session_id`, `document_id`, `structure_id`, `item_id`, `viewer_session_id`, `note_id`, `report_id`, `notification_id`, `work_record_id`, `advice_id`, `watched_file_id`, `candidate_id`, `local_action_id`를 노출한다.
- 외부 참조용 ID는 변경하지 않는다.
- 물리 삭제보다 상태 변경을 우선한다.
