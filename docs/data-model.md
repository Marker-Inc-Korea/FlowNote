# FlowNote 데이터 모델

이 문서는 2026-07-16 현재 WPF `FlowNoteLocalDatabase`와 FastAPI `app/db/models.py` 기준이다. 구현 전 모델은 “후속 외부 연동” 절에서만 예외로 다룬다.

## WPF 로컬 SQLite

기본 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 설정되면 해당 위치를 우선한다.

현재 WPF 로컬 DB의 주 테이블은 다음과 같다. 이 목록은 새 코드에서 사용하는 `FieldComment` 기준 테이블과 현재 기능 테이블을 기준으로 한다.

| 테이블 | 역할 |
| --- | --- |
| `user_accounts` | 로그인 계정, 표시 이름, role, 그룹/상위자, 상태 |
| `user_groups` | 관리자 그룹과 라인별 작업조 |
| `document_folders` | 루트, 기본 폴더, 분류/날짜 폴더 |
| `documents` | 로컬 문서 메타데이터, 최신 버전, 공개 버전, 서버 ID |
| `document_versions` | 문서 버전, 파일 경로, 변경 사유, 공개 여부, 서버 버전 ID |
| `field_comments` | 현장 코멘트 원천 기록과 서버 코멘트 ID |
| `field_comment_attachments` | FieldComment 첨부 파일 로컬 경로와 서버 첨부 ID |
| `document_view_logs` | 문서 열람 시작/종료, 자동 닫힘, 다운로드 차단 로그 |
| `activity_history` | 폴더, 문서, 사용자, 파일 감시, 동기화, 작업순서 이력 |
| `file_watch_candidates` | 관리자 파일 감시 후보 |
| `tag_definitions` | 태그 사전 |
| `document_tags` | 문서-태그 연결 |
| `notifications` | 문서/FieldComment/작업순서 알림 |
| `server_notification_cursors` | WPF 서버 scope·사용자별 마지막 성공 알림 cursor, 서버 관측 cursor, 초기 따라잡기/역행 상태, 갱신·관리자 초기화 정보 |
| `server_notification_messages` | WPF 서버 scope·사용자별 처리 완료 `message_id` 멱등 이력 |
| `work_sequence_boards` | 작업순서 보드 |
| `work_sequence_items` | 작업순서 항목과 상태 |
| `work_sequence_change_history` | 작업순서 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `report_sources` | 로컬 보고서 문서가 근거로 삼은 FieldComment, 문서, 작업순서 항목/이력 |
| `server_sync_queue` | 서버 전송 대기/실패/성공 상태 |
| `server_id_mappings` | 로컬 ID와 서버 ID 매핑 |
| `server_sync_migration_audit` | 보존 FAILED 큐의 승인 전환 감사. 원천 큐/ID/action/idempotency key와 신규 큐/ID/action/idempotency key, 승인자, plan hash, 원천 JSON snapshot, 구 명칭을 무손실 연결. dry-run이나 일반 앱 초기화에서는 만들지 않고 승인 실행 시 필요한 경우 생성 |

기존 공통 SQLite에는 FieldComment 명칭 전환 전에 만들어진 호환/잔존 테이블도 남아 있을 수 있다.

| 테이블 | 역할 |
| --- | --- |
| `field_notes` | 구 FieldNote 원천 기록. 새 작업에서는 사용하지 않으며 FieldComment 전환 또는 별도 마이그레이션 검토 대상 |
| `field_note_attachments` | 구 FieldNote 첨부 기록. 새 작업에서는 사용하지 않으며 FieldComment 첨부 전환 또는 별도 마이그레이션 검토 대상 |

2026-07-09 현재 공통 개발 DB `data/local/flownote.local.sqlite`에는 누적 테스트 기록으로 `field_notes` 345건, `field_note_attachments` 20건이 남아 있다. 이 데이터는 테스트 기록 보존 원칙에 따라 삭제하지 않는다. 현재 WPF 동기화 코드는 `server_sync_queue`의 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 항목을 자동 서버 전송 대상에서 제외하고 “구 FieldNote 큐”로 분류한다.

## FastAPI 서버 SQLite

2026-07-16 현재 ORM은 아래 47개 테이블을 생성 기준으로 사용한다.

서버 기본 DB 경로는 `services/api/data/flownote.sqlite3`이고 테스트 DB 기본 경로는 `services/api/data/flownote.test.sqlite3`이다. 서버 파일은 기본적으로 `services/api/storage/` 아래 저장된다.

서버 ORM 테이블은 다음과 같다.

| 테이블 | 역할 |
| --- | --- |
| `schema_migrations` | 스키마 적용 버전 기록 |
| `user_accounts`, `roles`, `user_roles` | 계정과 역할 기반 권한 |
| `auth_sessions` | access token ID, refresh token hash, 세션 만료/폐기 상태, Android 승인 단말 `device_id` |
| `operator_profiles` | 작업자/작업그룹/대리 입력 주체 |
| `file_objects` | 서버 로컬 파일 참조, MIME, 크기, SHA-256 |
| `documents`, `document_versions` | 문서, 버전, 최신/공개 버전. 문서와 개별 버전의 재시도 idempotency key를 각각 유일하게 보존 |
| `tag_definitions`, `document_tags` | 태그 사전과 문서 연결 |
| `terminal_devices` | Android 현장 단말기 승인 기준 정보 |
| `field_comments`, `field_comment_attachments` | 현장 코멘트와 첨부. 원천 기록과 개별 첨부의 재시도 idempotency key를 각각 유일하게 보존. 담당자, 검토 기한, 마지막 전이 사유, 선정 시각은 관리자 해석 영역으로 분리 |
| `comment_templates` | 정형 코멘트 문구 |
| `work_records`, `work_record_versions` | 작업내역 모델 기반 |
| `work_sequence_boards`, `work_sequence_items` | 작업순서 보드와 항목 |
| `work_sequence_change_history` | 작업순서 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `notification_channels` | 라인, 설비, 공정, 작업조, 작업내역 단위 업무 채널 |
| `notification_channel_members` | 채널별 사용자 멤버십, 역할, 마지막 읽음 위치 |
| `channel_messages` | 문서, FieldComment, 작업순서, 보고서, 인수인계 원천 이벤트 메시지 |
| `handovers` | 인수인계 원문, 원천 연결, 채널 연결, 전체 상태 |
| `handover_receipts` | 수신자별 인수인계 읽음, 확인, 후속조치 필요 상태 |
| `reports`, `report_sources` | 보고서와 근거 연결 |
| `ai_search_candidates` | 안정된 candidate ID와 content hash를 가진 AI 자동 조언 전 단계의 근거 검색 후보 read model |
| `ai_search_evaluation_runs` | 외부 AI 없는 ground-truth 회귀 실행과 provider 착수 판단 지표 |
| `ai_search_evaluation_cases` | 질문별 기대/실제 근거, 제외 사유, 순위 hash와 통과 여부 |
| `ai_search_ground_truth_cases` | 고객·현장·라인·DB scope별 사람이 승인한 질문 범주, 정상/제외/상충 유형, 기대/제외 근거, 허용 순위와 시점 기준 |
| `ai_provider_onboarding_reviews` | provider/model별 계약·데이터 처리·전송·TLS·장애·비용·kill switch 체크리스트와 기술/보안/법무/고객 착수 결정 |
| `ai_queries`, `ai_query_evidence_candidates`, `ai_query_citations` | 외부 AI 질의 상태와 질의 시점 근거 snapshot, 검증된 주장별 인용 연결 |
| `ai_prompt_versions`, `ai_call_attempts`, `ai_transfer_approvals` | 승인 프롬프트 버전, 정제된 호출 시도 감사, 고객·현장별 외부 전송 승인 |
| `ai_sensitive_data_policies` | 고객·현장별 활성 금칙어와 고객 식별자 정책 버전 |
| `ai_operational_policies` | 전역·현장별 kill switch, 요청·동시성·timeout·비용 한도, 보존과 감사 내보내기 정책 |
| `ai_operation_audit_events` | 승인·프롬프트·운영 정책 변경과 호출 전 차단의 정제 감사 이벤트 |
| `ai_retention_audits` | 만료 질의 payload 비식별화와 응답 원문 삭제 결과, 보존 hash 감사 |
| `document_access_logs` | 서버 문서 접근 로그 |
| `controlled_copy_grants` | SHA-256으로 저장한 1회성 토큰, 사용자·세션·단말·문서 버전, 만료·소비·실패 상태 |
| `android_document_view_grants` | Android 앱 내부 열람용 token hash, 사용자·세션·필수 승인 단말·공개 버전·미디어 종류·크기·SHA-256, 만료·소비·실패 상태 |
| `activity_history` | 서버 활동 이력 |

채널 메시지는 별도 개인 DM이나 개인 메신저 수집이 아니라 업무 채널 멤버십 기준으로 조회된다. 사용자별 알림 목록과 읽음 처리는 `channel_messages`와 `notification_channel_members.last_read_message_id`, `last_read_at`를 함께 사용한다.

`terminal_devices`는 개인 휴대폰 자동 등록 테이블이 아니라 승인된 현장 태블릿 또는 러기드 단말의 운영 기준이다. 단말 용도 `device_mode`는 현장 열람용 `viewer`와 관리 지원용 `admin_support`를 사용한다. 상태는 `ACTIVE`, `INACTIVE`, `RETIRED`이고 폐기 단말은 재활성화하지 않는다. `registered_by`, `updated_by`는 등록자와 마지막 변경자, `replaced_device_id`는 교체 단말이 대체한 기존 단말 ID를 보존한다. Android 앱은 로그인 시 `deviceId`를 보내며, 서버는 같은 ID가 `terminal_devices.device_id`에 있고 `status = ACTIVE`일 때만 세션을 만든다. 성공한 Android 세션은 `auth_sessions.device_id`에 단말 ID를 남기고 로그인 성공 때마다 `terminal_devices.last_seen_at`을 갱신한다. 등록, 정보 변경, 비활성화, 폐기, 교체 이력은 `activity_history`의 `terminal_device.*` 이벤트로 추적한다.

Android 로컬 DB `flownote_android_outbox.db`는 장기 기준 데이터가 아니다. 네트워크 불안정 구간의 FieldComment와 사진 첨부 재전송을 위해 `local_id`, `kind`, Keystore AES-GCM 암호문인 `payload`, `idempotency_key`, 새 첨부의 앱 내부 암호화 파일 참조, 서버 `comment_id`, 상태, 시도 횟수, 마지막 시도 시각과 마지막 오류를 임시 보관한다. 새 사진은 선택 즉시 `filesDir/outbox-attachments/`의 AES-GCM 암호문으로 가져오며, 기존 설치에서 남은 persist URI는 전송 완료까지 읽기 호환만 유지한다. `PENDING`, `FAILED` 항목은 최대 12회 자동 시도하며 재시도 간격은 시도 횟수에 따라 `15초 → 30초 → 60초`로 증가하고 최대 15분으로 제한한다. 재전송 성공 후 서버 원천 ID를 연결하고 `SYNCED`로 전환하며 `SYNCED` 항목과 최대 시도 횟수에 도달한 항목은 자동 재전송하지 않는다.

서버의 `documents`, `document_versions`, `field_comments`, `field_comment_attachments`, `document_access_logs`, `reports`는 각 생성 단위의 선택적 `idempotency_key`를 최대 160자로 저장하고 유일 인덱스로 보호한다. 앱 시작 시 기존 SQLite에도 누락된 열과 유일 인덱스를 보완한다. 동일 키 재요청은 같은 부모 원천에 속할 때 기존 row를 반환하고, 다른 문서나 FieldComment에 사용된 키는 충돌로 거부해 재시도 중복 파일과 중복 이력을 막는다.

`field_comments`의 원천 핵심 필드는 생성 후 ORM 수준에서 불변이며, 원천 row 자체의 ORM 삭제도 거부한다. 오입력·중복·근거 부적합 기록은 삭제하지 않고 검토 상태 `EXCLUDED`로 분류해 이력을 보존한다. API 응답의 `source_hash_sha256`은 원천 snapshot을 정렬 JSON으로 직렬화해 계산한다. 관리자 검토 변경은 `activity_history.before_value/after_value`에 검토 snapshot과 같은 원천 hash를 저장하고 `actor_id`, `change_reason`으로 전이와 되돌림을 추적한다.

보고서 `FIELD_COMMENT` source는 `SELECTED` 상태만 저장하며 `source_version_id`에 FieldComment가 관찰한 문서 버전을 복사한다. `DOCUMENT` source는 문서의 현재 `published_version_id`와 같은 공개 버전만 저장한다. 따라서 `field_comments → activity_history → report_sources → reports.generated_document_id → document_versions`를 ID와 hash 손실 없이 역추적할 수 있다. 활성 `notification_channels`가 원천에 연결된 경우 보고서 저장 actor의 활성 멤버십도 검사한다.

`controlled_copy_grants`는 원본 토큰 대신 `token_hash`만 저장한다. 각 grant는 공개 문서와 정확한 공개 버전, 요청 사용자, `auth_sessions.session_id`, 선택적 승인 단말 ID, 발급 시점의 파일 크기와 SHA-256에 묶인다. 상태는 `ISSUED`, `CONSUMED`, `EXPIRED`, `FAILED`이며 기본 60초(설정값은 5~300초로 정규화) 안에 한 번만 소비할 수 있다. 스트리밍 시작 전 상태를 원자적으로 `CONSUMED`로 바꾸고, 이후 공개 상태·저장 경로·크기·SHA-256 검사가 실패하면 `FAILED`와 정제된 실패 사유를 남긴다.

`android_document_view_grants`도 원본 token을 저장하지 않고 SHA-256 hash만 보존한다. controlled copy와 달리 `device_id`가 필수이며 `media_kind`, 정규화 MIME type, 발급 시 파일 크기와 SHA-256을 고정한다. 상태는 `ISSUED`, `CONSUMED`, `EXPIRED`, `FAILED`이고 1회 스트림 시작 전에 원자적으로 소비한다. `document_access_logs`와 `activity_history`에는 grant 발급, 스트림 시작·완료, 실패·차단·만료를 사용자·단말·문서 버전과 함께 남긴다. Android 내부 난수 캐시 파일은 서버 기준 데이터가 아니며 DB 모델로 관리하지 않는다.

보고서 서버 저장 실패는 WPF 전용 큐를 새로 만들지 않고 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남긴다. 큐는 한글 실패 사유, `last_attempt_at`, `attempt_count`를 기존 동기화 항목과 같은 방식으로 기록한다.

로컬 보고서 문서는 `documents.document_type = Report`인 문서이며, 선택한 근거는 로컬 `report_sources.local_report_document_id`로 연결한다. 재시도 성공 시 `documents.server_report_id`, `documents.server_document_id`, 최신 `document_versions.server_version_id`, `server_id_mappings(entity_type IN ('report', 'document', 'document_version'))`를 채운다.

## AI 검색 근거 후보 read model

AI 자동 조언과 자동 의사결정은 아직 범위에 넣지 않는다. 서버는 먼저 `ai_search_candidates` read model에 근거가 있는 검색과 요약 후보만 만든다. 이 테이블은 외부 AI API 호출 결과가 아니라 현재 DB 원천에서 재생성할 수 있는 검색 후보 목록이다. WPF `AI 근거 후보 운영 점검` 화면은 이 read model의 재생성, 품질 지표, 제외 사유, 후보 목록, 원천 추적값을 조회한다.

후보 원천은 다음 네 종류로 제한한다.

| `source_type` | 생성 기준 | 제외 기준 | 화면 역추적 |
| --- | --- | --- | --- |
| `PUBLISHED_DOCUMENT_VERSION` | `documents.status = PUBLISHED`, `documents.published_version_id = document_versions.version_id`, `document_versions.version_status = PUBLISHED`, `document_versions.is_published = true` | 공개되지 않은 문서/버전, 삭제된 문서 | `trace_table = document_versions`, `trace_id = document_id`, `trace_version_id = version_id` |
| `FIELD_COMMENT` | `field_comments.status`가 `EXCLUDED`, `ARCHIVED`가 아니고 원문/정리/분석 내용 중 하나 이상이 있음 | `EXCLUDED`, `ARCHIVED`, 빈 내용, `input_mode = mes_integration` | `trace_table = field_comments`, `trace_id = comment_id`, `trace_version_id = document_version_id` |
| `WORK_SEQUENCE_HISTORY` | `work_sequence_change_history`의 변경 유형, 이전 값, 이후 값, 변경 사유 중 하나 이상이 있음 | 역추적 텍스트가 모두 비어 있음 | `trace_table = work_sequence_change_history`, `trace_id = change_id` |
| `REPORT_SOURCE` | `reports.status != ARCHIVED`이고 실제 원천이 남아 있는 보고서의 `report_sources` row | 보고서가 없거나 보관 상태인 source, 원천 식별자가 비어 있음, 원천 row가 없거나 제외 상태임, `DOCUMENT` 원천이 삭제 상태임 | `trace_table = report_sources`, `trace_id = report_sources.id`, `trace_version_id = source_version_id` |

`ai_search_candidates`의 `candidate_id`는 `source_type + source_id + source_version_id`로 결정되는 안정 식별자이고 `content_hash`는 검색 본문의 SHA-256이다. 원문 화면 이동은 `source_type`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `parent_type`, `parent_id`를 함께 사용한다. 보고서 source는 원천의 원천을 직접 후보 ID로 삼지 않고 `report_sources.id`를 후보 `source_id`로 삼아 보고서가 어떤 근거를 어떤 관계로 사용했는지 먼저 추적한다.

`ai_search_ground_truth_cases`는 고객·현장·선택적 라인과 로컬 경로를 노출하지 않는 DB fingerprint scope에 묶인다. 질문 범주는 안전, 품질, 설비 이상, 작업 보류, 재작업, 인수인계, 최신 공개 문서, 상충 기록이고 각 범주에서 `NORMAL`, `EXCLUSION`, `CONFLICT`를 구분한다. 기대 포함 근거는 승인 시점의 candidate/source/version/trace ID와 content hash, 승인자의 열람 권한, `as_of` 이전 존재를 검증한 뒤 snapshot으로 고정한다. 제외 근거도 실제 원천 row로 역추적되어야 한다. 허용 순위 최소·최대, `as_of`, 승인자·승인 시각을 보존하며 승인 질문 원본을 평가 실행과 분리한다.

`ai_search_evaluation_runs`는 실행 ID/라벨, 요청자와 평가 대상 사용자, ID/hash·순위 안정성, scope, precision@k, recall@k/top-k 포함률, 제외 원천 노출, 권한 누출, 존재하지 않는 인용, citation trace·의미 일치, 상충 표시율과 provider 착수 가능 지표를 보존한다. `ai_search_evaluation_cases`는 질문, 기대/실제 `SUFFICIENT` 또는 `INSUFFICIENT_EVIDENCE`, 기대 근거 JSON, 실제 candidate/source/version/trace/content hash snapshot, 제외 근거와 사유, ranking hash를 보존한다. 테스트와 사람형 스모크의 회귀 기록이므로 자동 삭제하지 않는다.

`ai_provider_onboarding_reviews`는 고객·현장·provider·model·review version을 유일하게 묶는다. 체크리스트 JSON은 계약 조건, provider 보존 기간, 학습 사용 여부, 전송/처리 지역, TLS, timeout, 429, 5xx, 비용 한도, kill switch, 법무 승인, 고객 승인을 각각 `PENDING`/`PASS`/`FAIL`과 근거 참조로 보존한다. 기술·보안·법무·고객 상태는 `PENDING`/`APPROVED`/`REJECTED`, 검토자와 시각을 별도로 기록한다. 새 심사는 기존 row를 덮어쓰지 않고 새 version을 만들며 체크리스트 전건 `PASS`와 네 영역 `APPROVED`가 함께 있어야 착수 승인이다.

품질 점검은 후보 수와 제외 사유를 함께 산출한다. `REPORT_SOURCE`의 `DOCUMENT` 원천은 `documents.status != DELETED`와 `documents.deleted_at IS NULL`을 모두 만족해야 하며, 버전 ID가 있으면 그 버전이 같은 문서에 속하는지도 확인한다. 조건을 만족하지 않으면 `report_source_missing_origin`으로 집계한다. FieldComment 검토 품질은 전체 상태별 개수, `ANALYZED`/`REVIEWED`/`SELECTED` 합계, AI 착수 최소 기준 100건 대비 부족분을 표시한다. FieldComment가 대부분 `NEW`라면 검색 후보에는 들어갈 수 있어도 요약 신뢰도와 AI 착수 기준은 부족한 것으로 본다.

MES/ERP 어댑터는 후속 범위이므로 검색 후보 생성은 `work_records.external_system`, `external_ref_id` 같은 외부 연동 필드를 사용하지 않는다. `mes_integration` 입력으로 들어온 FieldComment도 어댑터 정책이 정해지기 전에는 후보에서 제외한다.

## 외부 AI 질의와 호출 로그 안전장치

다음 모델은 외부 AI 1단계의 안전장치와 감사 골격으로 구현되었다. provider 중립 fake/recording adapter와 제한형 JSON 네트워크 adapter가 있으며, 네트워크 adapter는 `test` 환경의 별도 명시 설정에서만 생성된다. 기본 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`와 `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=DISABLED`는 모든 외부 호출 시도를 차단한다. 기존 `ai_search_candidates`는 외부 AI 설정과 무관하게 재생성 가능한 read model로 유지한다.

| 테이블 | 주요 필드 | 역할과 보존 기준 |
| --- | --- | --- |
| `ai_queries` | `query_id`, `requested_by`, `query_text`, `query_hash`, `purpose`, `status`, `prompt_version_id`, `response_storage_mode`, `response_text`, `response_hash`, `retention_until`, `response_retention_until`, `regeneration_of_query_id`, `regenerable_until`, `block_code`, `created_at`, `completed_at` | 질의, 호출 사용자, 처리 상태와 응답 저장 여부의 기준 row. 필터 통과 질의는 마스킹된 문구를 저장하고 전송 금지 질의는 `[REDACTED]`와 hash만 남긴다. 응답은 기본 `DO_NOT_STORE`이며 본문 대신 hash를 남긴다. 만료 시 서버 스케줄러 또는 `system-admin` 수동 실행이 질의 payload를 `[EXPIRED]`로 비식별화하고 저장 응답 원문을 삭제한다. |
| `ai_query_evidence_candidates` | `id`, `query_id`, `candidate_id`, `source_type`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `rank`, `selected_for_prompt`, `sent_externally`, `content_hash`, `eligibility_result`, `exclusion_reason` | 질의 시점의 적격·제외 후보 ID와 순위, provider 경계 전달 여부, 원천 식별자와 content hash snapshot. 제외 후보도 원문 없이 `EXCLUDED`와 `SOURCE_FORBIDDEN`/`CONTENT_RESTRICTED` 사유를 남기며 provider DTO에는 포함하지 않는다. |
| `ai_query_citations` | `citation_id`, `query_id`, `claim_key`, `candidate_id`, `source_type`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `internal_source_uri`, `content_hash`, `validated_at` | 반환한 각 사실 주장과 문서 버전, FieldComment, 작업순서 이력 또는 `report_sources.id`의 연결. 1년 보존은 후속 운영 정책이다. |
| `ai_prompt_versions` | `prompt_version_id`, `name`, `version`, `template_hash`, `template_text`, `allowed_purpose`, `created_by`, `approved_by`, `approved_at`, `retired_at` | 재현 가능한 불변 프롬프트 버전. 승인 후 내용을 덮어쓰지 않고 새 버전을 만든다. |
| `ai_call_attempts` | `attempt_id`, `query_id`, `provider`, `model`, `provider_request_id`, `status`, `started_at`, `finished_at`, `http_status`, `error_code`, `sanitized_error_message`, `input_units`, `output_units` | 최초 호출과 timeout/429/5xx 재시도를 요청 ID에 연결하는 호출 및 오류 로그. 일반 로그에는 원문 프롬프트, 근거 본문, 응답, 자격증명이나 provider raw body를 넣지 않고 정제한 메타데이터를 남긴다. 1년 보존은 후속 운영 정책이다. |
| `ai_transfer_approvals` | `approval_id`, `customer_scope`, `site_scope`, `provider`, `model_scope`, `allowed_source_types`, `data_handling_policy_version`, `approved_by`, `approved_at`, `expires_at`, `revoked_at`, `reason` | 고객·현장별 외부 전송 승인. 만료·철회 시 새 호출을 즉시 차단하며 `admin` 또는 `system-admin`의 승인 주체와 근거를 보존한다. |
| `ai_sensitive_data_policies` | `policy_id`, `customer_scope`, `site_scope`, `version`, `forbidden_terms_json`, `customer_identifiers_json`, `is_active`, `created_by`, `created_at` | 고객·현장별 사용자 정의 금칙어와 고객 식별자 정책. 최신 활성 정책 하나를 query snapshot 필터에 적용하며 원문 검출값은 감사 로그에 남기지 않는다. |

`response_storage_mode`는 `DO_NOT_STORE`, `STORE_90_DAYS`만 허용한다. 기본값은 `DO_NOT_STORE`이며 이때 응답 본문은 요청 세션에 반환한 뒤 저장하지 않는다. `STORE_90_DAYS`는 본문과 별도 `response_retention_until`을 저장한다. 서버 lifespan 스케줄러와 `system-admin` 즉시 실행 API는 만료된 질의 문구를 `[EXPIRED]`로 비식별화하고 저장 응답 원문을 삭제하되 query/response hash, 근거·인용·호출 메타데이터와 `ai_retention_audits`를 보존한다. 질의 재생성 API는 아직 없으며, 후속 재생성은 같은 질의, 불변 프롬프트 버전, 근거 후보 ID와 content hash, provider/model을 다시 사용하되 원천의 권한·공개·외부 전송 승인 상태를 다시 평가해야 한다.

`ai_query_evidence_candidates.candidate_id`는 재생성 가능한 read model에 대한 논리적 역추적 키이며 물리 FK로 묶지 않는다. `ai_search_candidates` 재생성 뒤에도 질의 시점의 source/version/trace ID와 content hash snapshot을 보존하기 위한 결정이다.

상태는 `RECEIVED`, `BLOCKED`, `CALLING`, `SUCCEEDED`, `INSUFFICIENT_EVIDENCE`, `CITATION_VALIDATION_FAILED`, `FAILED`를 사용한다. 경계 차단은 `CONTENT_RESTRICTED`, `SOURCE_FORBIDDEN`, `APPROVAL_REVOKED`, `INSUFFICIENT_EVIDENCE` 같은 정제 코드를 사용한다. 응답의 사실 주장은 최소 한 개의 `ai_query_citations`와 연결되어야 한다. 허용되는 원천 식별자는 문서의 `document_id + version_id`, FieldComment의 `comment_id`와 연결된 `document_version_id`(있는 경우), 작업순서 이력의 `change_id`, 보고서 근거의 `report_sources.id + source_type + source_id + source_version_id`다. 후보가 0건이면 본문 없이 `INSUFFICIENT_EVIDENCE`를 반환하고, 인용이 누락되거나 snapshot에 없는 후보 ID를 사용하면 응답 본문을 저장·노출하지 않고 `CITATION_VALIDATION_FAILED`를 반환한다.

## 작업지시와 후속 외부 연동 필드

초기 작업지시는 관리자가 FlowNote에 직접 입력하는 수동 데이터가 기준이다. MES/ERP 어댑터는 후속 대상이며, 외부 시스템이 생기더라도 FlowNote의 현장 기록은 수동 입력 모델과 같은 연결 필드를 사용한다.

### 초기 수동 입력 기준

| 엔티티 | 필드 | 용도 |
| --- | --- | --- |
| `work_records` | `work_record_id` | FlowNote 내부 작업내역 식별자 |
| `work_records` | `work_order_no` | 관리자가 입력한 작업지시 번호 또는 현장 식별 번호 |
| `work_records` | `title` | 작업명, 품목/공정이 섞인 현장 표시명 |
| `work_records` | `work_instruction_document_id` | 작업지시 문서, 기준서, 도면 등 연결 문서 ID |
| `work_records` | `source_type` | 초기 수동 입력은 `manual`, 후속 외부 수신은 `external` |
| `work_records` | `status` | `DRAFT`, `ACTIVE`, `COMPLETED`, `ARCHIVED` |
| `work_record_versions` | `summary`, `result_note`, `issue_note`, `action_note` | 작업 수행 요약, 결과, 문제점, 조치 기록 |
| `work_sequence_boards` | `line_code`, `board_date` | 라인 또는 작업장과 작업 날짜 |
| `work_sequence_items` | `work_order_no`, `document_id`, `assigned_to`, `status`, `hold_reason` | 작업순서 항목과 작업지시 번호, 관련 문서, 담당자, 상태, 보류 사유 연결 |
| `field_comments` | `document_id`, `work_record_id`, `input_mode` | 문서 또는 작업내역에 연결된 현장 원천 기록. MES 수신으로 생긴 기록은 후속 단계에서 `mes_integration`을 사용할 수 있다. |
| `reports` | `work_record_id`, `report_sources` | 보고서가 어떤 작업내역과 원천 근거를 정제했는지 추적 |

### MES/ERP 어댑터 연결 기준

후속 어댑터는 외부 작업지시를 새 도메인으로 따로 만들기보다 `work_records`와 `work_sequence_items`의 연결 필드를 우선 사용한다.

| 외부 데이터 | FlowNote 연결 필드 | 기준 |
| --- | --- | --- |
| 외부 시스템명 | `work_records.external_system`, `tag_definitions.external_system` | 예: `MES`, `ERP`, 현장 시스템 약칭 |
| 외부 작업지시 ID | `work_records.external_ref_id` | 외부 원천 레코드의 불변 ID. 화면 표시용 작업번호와 다를 수 있다. |
| 작업지시 번호 | `work_records.work_order_no`, `work_sequence_items.work_order_no` | 현장 사용자가 아는 번호를 유지한다. |
| 작업명/품목/공정 표시 | `work_records.title`, 태그 | 품목, 설비, 공정은 태그로 보완 연결한다. |
| 작업지시 문서 | `work_records.work_instruction_document_id`, `work_sequence_items.document_id` | FlowNote에 등록된 문서 ID를 연결한다. |
| 작업 상태 | `work_records.status`, `work_sequence_items.status` | 외부 상태를 그대로 강제하지 않고 FlowNote 상태 값으로 매핑한다. |
| 보류/재작업/현장 이슈 | `work_sequence_items.hold_reason`, `field_comments`, `work_record_versions.issue_note` | 현장 경험 기록을 외부 정형 데이터보다 우선 보존한다. |

어댑터가 도입되어도 외부 시스템 수신 실패나 지연은 문서 열람, FieldComment 작성, 작업순서 수동 변경, 보고서 작성 흐름을 막지 않아야 한다. 외부 시스템으로 상태를 되돌려 쓰는 양방향 동기화는 별도 설계 결정 후에만 다룬다.

## 상태 값

문서 상태:

- `WORKING`
- `IN_REVIEW`
- `PUBLISHED`
- `ARCHIVED`

서버 ORM의 `documents.status` 제약에는 `DELETED`도 포함된다. 일반 상태 PATCH는 `DELETED`를 받지 않고 전용 DELETE API가 `status = DELETED`, `deleted_at`, 공개 포인터 해제와 감사를 한 transaction에서 처리한다.

`documents.revision`은 서버가 단독으로 증가시키는 문서 aggregate revision이다. 최초 등록은 1이며 새 버전, 문서 상태, 버전 상태, 공개본 교체, soft delete처럼 서버 기준 상태가 실제로 바뀔 때 한 번 증가한다. WPF의 로컬 `version_no`나 수정 시각으로 대체하지 않는다. WPF는 마지막 서버 확인값을 `documents.server_revision`, `documents.server_version_id`, `documents.server_published_version_id`에 보관하고 큐 생성 시 기준값을 복사한다.

문서 상태 전이는 `WORKING → IN_REVIEW|ARCHIVED`, `IN_REVIEW → WORKING|ARCHIVED`, `PUBLISHED → IN_REVIEW|ARCHIVED`, `ARCHIVED → WORKING|IN_REVIEW`만 상태 API에서 허용한다. `PUBLISHED` 진입은 publish API만 수행한다. `DELETE /documents/{document_id}`는 `DELETED`, `deleted_at`, 공개 포인터 해제를 같은 revision 변경으로 처리하며 삭제된 서버 문서는 로컬 재전송으로 암묵 복구하지 않는다.

서버 문서 버전 상태:

- `WORKING`
- `IN_REVIEW`
- `APPROVED`
- `PUBLISHED`
- `SUPERSEDED`
- `ARCHIVED`

FieldComment 상태:

- `NEW`
- `NEEDS_REVIEW`
- `ANALYZED`
- `REVIEWED`
- `SELECTED`
- `EXCLUDED`
- `ARCHIVED`

서버 작업내역 상태:

- `DRAFT`
- `ACTIVE`
- `COMPLETED`
- `ARCHIVED`

서버 작업순서 보드 상태:

- `ACTIVE`
- `ARCHIVED`

작업순서 항목 상태:

- `WAITING`
- `IN_PROGRESS`
- `HOLD`
- `COMPLETED`

FastAPI `ITEM_STATUSES`, 서버 ORM 제약, WPF `WorkSequenceService`, WPF 관리자/TV 화면은 위 네 상태를 정식 상태로 사용한다. 2026-07-09 현재 공통 개발 DB에는 테스트 실행 중 직접 삽입된 `TODO` 상태 작업순서 항목 3건이 남아 있지만, 새 코드와 API의 허용 상태는 아니므로 새 기능과 문서에서는 `WAITING`을 대기 상태로 사용한다. 해당 row는 테스트 기록 보존 원칙에 따라 삭제하지 않고 잔존 데이터로 분류한다.

작업순서 알림 후보 상태:

- `CANDIDATE`
- `SENT`
- `DISMISSED`

서버 동기화 큐 상태:

- `PENDING`
- `FAILED`
- `CONFLICT`
- `SYNCED`
- `DISCARDED`

`server_sync_queue`는 문서 작업에 대해 `base_server_revision`, `expected_server_version_id`, `expected_published_version_id`, `local_file_hash_sha256`를 생성 시점 snapshot으로 보존한다. 409는 일반 전송 실패와 분리해 `CONFLICT`와 `conflict_code`, 원 응답을 기록한다. 공개·문서 상태 구 큐의 `base_server_revision`이 null이면 WPF가 서버 호출 전에 `LEGACY_BASE_MISSING` 충돌을 만들며 현재 revision을 임의 대입하지 않는다. 관리자 해결 뒤 로컬 요청을 최신 서버 revision에서 다시 보내면 `resolution_action = RETRY_LOCAL_ON_LATEST`, 서버본 유지로 폐기하면 `DISCARDED`와 `resolution_action = KEEP_SERVER`를 사용한다. 두 경로 모두 사유, 해결자, 해결 시각과 `activity_history` 감사를 남기며 앱 재시작 뒤에도 유지한다. 큐 요약의 전체 건수에는 감사 종결 상태인 `DISCARDED`를 포함하지만 운영 지표의 처리 대기 깊이에서는 제외한다.

문서·공개 버전 불변조건:

- `documents.latest_version_id`는 같은 문서에서 유일하게 `is_latest = true`인 버전을 가리키고 버전 번호는 감소하지 않는다.
- `documents.status = PUBLISHED`이면 `published_version_id`는 null이 아니며 같은 문서의 `version_status = PUBLISHED`, `is_published = true`인 정확히 한 버전을 가리킨다.
- publish 전에 서버 저장 파일을 다시 읽어 `file_objects.hash_sha256`과 비교한다. 불일치나 파일 누락은 `FILE_HASH_MISMATCH` 충돌이며 공개 포인터를 바꾸지 않는다.
- 같은 idempotency key의 동일 내용 재시도는 기존 결과를 반환한다. 파일 hash나 핵심 메타데이터가 다르면 `IDEMPOTENCY_KEY_REUSED`로 거부한다.
- 기존 `field_notes`, `field_note_attachments`와 구 큐는 삭제·rename·자동 덮어쓰지 않는다. 읽기 전용 dry-run과 row별 관리자 승인으로 새 FieldComment 원천/큐를 별도 생성하며 원천 snapshot을 감사에 남긴다.

채널/인수인계 상태:

- 채널 유형: `LINE`, `EQUIPMENT`, `PROCESS`, `WORK_GROUP`, `HANDOVER`, `WORK_RECORD`, `CUSTOM`
- 채널 메시지 유형: `NOTICE`, `DOCUMENT_EVENT`, `FIELD_COMMENT_EVENT`, `WORK_SEQUENCE_EVENT`, `HANDOVER`, `SYSTEM`
- 인수인계 상태: `DRAFT`, `SENT`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`, `ARCHIVED`
- 인수인계 수신 상태: `UNREAD`, `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`

채널 메시지와 인수인계 source는 문서, FieldComment, 작업순서 항목/이력, 작업내역, 보고서, 인수인계 원천 ID를 보존한다. 개인 DM, 개인 메신저 수집, GPS, 근태 상태는 이 모델에 포함하지 않는다.

서버 보고서 상태:

- `DRAFT`
- `AI_DRAFTED`
- `REVIEWED`
- `APPROVED`
- `ARCHIVED`

서버 인증 세션 상태:

- `ACTIVE`
- `REVOKED`
- `EXPIRED`

## 외부 AI 운영·보존 모델

- `ai_transfer_approvals`: 고객/현장/provider/model/목적/source type, 처리정책 버전, 승인·만료·폐기 시각을 보존한다. 다른 고객/현장에는 재사용하지 않는다.
- `ai_prompt_versions`: 초안→검토→승인→활성→폐기 lifecycle과 template hash를 가진다. 승인된 본문은 수정하지 않고 새 version을 만든다.
- `ai_queries`: 고객/현장 scope, prompt/approval JSON snapshot을 질의 시점에 저장한다. 이후 운영 객체 변경은 과거 snapshot을 바꾸지 않는다.
- `ai_operational_policies`: 전역 `*/*` 또는 정확한 고객/현장 scope별 kill switch, 요청·동시성·timeout·비용, 보존과 감사 내보내기 정책이다. 비밀 컬럼은 없다.
- `ai_operation_audit_events`: 승인·프롬프트·정책 변경과 호출 전 차단 사유의 원문 없는 감사 이벤트다.
- `ai_retention_audits`: 만료 질의별 payload 비식별화와 응답 삭제 동작, 보존된 hash를 기록한다.

## 역할 값

현재 코드의 role 값은 다음과 같다.

- `admin`
- `system-admin`
- `document-admin`
- `manager`
- `assistant-manager`
- `department-manager`
- `line-foreman`
- `team-lead`
- `team-member`
- `viewer`

### 역할별 권한 정책

FastAPI 서버의 `app/core/auth.py`와 WPF `RolePermissionPolicy`는 다음 기준을 공유한다.

| 권한 영역 | FastAPI 기준 | WPF 기준 |
| --- | --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | 문서 등록, 파일 업로드, Drag & Drop, 상태 변경, 공개, 작업판 버튼 활성 |
| FieldComment 등록 | 문서 쓰기 role + `team-member`, `viewer` | 문서 뷰어의 현장 코멘트 작성은 기본 role 전체 허용 |
| 접근 로그 조회 | `admin`, `system-admin` | WPF는 로컬 열람/다운로드 차단 로그를 기록하고 서버 조회 UI는 아직 두지 않는다 |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | 보고서 버튼 활성 |
| 채널 관리/인수인계 확인 현황 | 채널 생성은 문서/작업순서 쓰기 role, 조회와 수신확인은 채널 멤버십 또는 `admin`, `system-admin` 기준 | 채널 관리와 인수인계 확인 현황 버튼은 문서 등록 권한과 같은 role에서 활성 |
| 파일 감시 | 서버 전용 권한 그룹은 아직 없음 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| controlled copy 다운로드 | 현재 공개 버전, 1회성 티켓, 사용자·세션 일치, 경로·크기·SHA-256 재검증 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| 사용자 관리 | 계정 생성·role/상태 변경·비밀번호 재설정·세션 조회/폐기 | `admin`, `system-admin` |

### 로컬 계정과 서버 계정 운영 기준

WPF 사용자 관리는 위 role 중 하나만 선택할 수 있다. 새 사용자 ID는 `user-{loginId}` 형식으로 자동 생성된다.

`user_accounts.must_change_password`는 임시 비밀번호 로그인 후 정상 API 사용을 막는 서버 기준 값이고 `password_changed_at`은 본인 비밀번호 변경 완료 시각이다. 계정 생성과 관리자 비밀번호 재설정은 `must_change_password = true`, 본인 변경 성공은 `false`로 바꾸며 모든 기존 세션을 폐기한다. `auth_sessions`에는 원문 refresh token이 아니라 hash만 저장하고, 계정 잠금·비활성화·role 변경·비밀번호 변경/재설정·관리자 폐기 시 즉시 `REVOKED`로 전환한다.

WPF 사용자 관리는 서버 로그인 세션이 있으면 서버 계정 운영 화면, 서버 URL 미설정 또는 연결 실패로 로컬 로그인한 경우에는 로컬 SQLite 계정 화면으로 분리한다. 두 계정 저장소를 자동 병합하거나 같은 ID의 row를 서로 덮어쓰지 않는다.

`FLOWNOTE_API_BASE_URL`이 설정되어 있고 서버 로그인이 성공하면 WPF 현재 세션의 사용자 ID, 로그인 ID, 표시 이름, role은 서버 응답을 우선한다. 같은 로그인 ID의 로컬 계정 정보가 다르더라도 서버 사용자 정보를 화면 표시, 버튼 권한, 서버 동기화 작성자 ID에 사용하고 로컬 계정 row는 자동 덮어쓰지 않는다.

서버가 401 또는 403으로 로그인 실패를 명확히 응답한 경우에는 로컬 계정 fallback으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.
