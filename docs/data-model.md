# FlowNote 데이터 모델

이 문서는 2026-08-15 현재 WPF `FlowNoteLocalDatabase`와 FastAPI `app/db/models.py` 기준이다. 문서 상태·검토·공개·태그와 FieldComment 검토/첨부, 보고서 aggregate 수렴 필드는 구현되었으며 현재 코드에 없는 나머지 필드는 `목표`로 명시한다.

## WPF 로컬 SQLite

기본 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다. `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`가 설정되면 해당 위치를 우선한다.

현재 WPF 로컬 DB의 주 테이블은 다음과 같다. 이 목록은 새 코드에서 사용하는 `FieldComment` 기준 테이블과 현재 기능 테이블을 기준으로 한다.

| 테이블 | 역할 |
| --- | --- |
| `user_accounts` | 로그인 계정, 표시 이름, role, 그룹/상위자, 상태 |
| `user_groups` | 관리자 그룹과 라인별 작업조 |
| `document_folders` | 루트, 기본 폴더, 분류/날짜 폴더 |
| `documents` | 로컬 문서 메타데이터, 최신/공개 버전, 서버 ID·revision·태그 집합과 보고서 content/source-set hash read-back |
| `document_versions` | 문서 버전, 파일 경로, 변경 사유, 공개 여부, 서버 버전 ID |
| `field_comments` | 현장 코멘트 원천 기록과 서버 코멘트 ID |
| `field_comment_attachments` | FieldComment 첨부 파일 로컬 경로와 서버 첨부 ID |
| `field_comment_saved_views` | WPF FieldComment 목록의 저장된 필터 이름·JSON·갱신 시각 |
| `document_view_logs` | 문서 열람 시작/종료, 미리보기 실패, 다운로드 차단과 구 자동 닫힘 호환 로그 |
| `activity_history` | 폴더, 문서, 사용자, 파일 감시, 동기화, 작업순서 이력 |
| `file_watch_candidates` | 관리자 파일 감시 후보 |
| `tag_definitions` | 태그 사전 |
| `document_tags` | 문서-태그 연결 |
| `notifications` | 문서/FieldComment/작업순서 알림 |
| `server_notification_cursors` | WPF 서버 scope·사용자별 마지막 성공 알림 cursor, 서버 관측 cursor, 초기 따라잡기/역행 상태, 갱신·관리자 초기화 정보 |
| `server_notification_messages` | WPF 서버 scope·사용자별 처리 완료 `message_id` 멱등 이력 |
| `server_bindings` | 정규화 서버 URL별 승인·관측 instance/epoch, schema/API contract 범위, 복구 pilot run·backup set·승인·담당자·장애 코드와 `ACTIVE`/`RECONCILIATION_REQUIRED`·수렴 상태 |
| `reconciliation_runs` | 서버 복구 경계 판정 run, 이전/현재 instance·epoch, trigger, 양쪽 cursor, 생성자·승인 사유와 상태 |
| `reconciliation_items` | 로컬 큐 inventory별 `CONFIRMED`/`ABSENT`/`DIVERGED` 판정, 제안·적용 조치, 승인 종결 상태, 서버 ID/revision/hash와 해결 감사 |
| `work_sequence_boards` | 작업순서 보드 |
| `work_sequence_items` | 작업순서 항목과 상태 |
| `work_sequence_change_history` | 작업순서 변경 이력 |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `report_sources` | 로컬 보고서 문서가 근거로 삼은 FieldComment, 문서, 작업순서 항목/이력과 고정 version/revision/hash 검증 상태 |
| `server_sync_queue` | 서버 전송 대기/실패/성공 상태 |
| `server_id_mappings` | 로컬 ID와 서버 ID 매핑 |
| `server_sync_migration_audit` | 보존 FAILED 큐의 승인 전환 감사. 원천 큐/ID/action/idempotency key와 신규 큐/ID/action/idempotency key, 승인자, plan hash, 원천 JSON snapshot, 구 명칭을 무손실 연결. dry-run이나 일반 앱 초기화에서는 만들지 않고 승인 실행 시 필요한 경우 생성 |

WPF DB에는 다음 수렴 필드가 additive 방식으로 구현되었다. 기존 큐·매핑·테스트 row를 새 테이블로 옮기거나 삭제하지 않는다.

| 구현 테이블/열 | 역할 |
| --- | --- |
| `field_comments.review_revision` | 로컬이 마지막으로 보유한 FieldComment 검토 revision. 기본값 1이며 서버 검토 성공 응답으로 갱신 |
| `server_sync_queue.base_domain_revision` | `field_comment_review` enqueue 시점의 로컬 `review_revision`. 다른 entity type은 현재 NULL |
| `server_sync_queue.intent_hash` | enqueue 시 `entity_type|entity_id|action|idempotency_key|base_domain_revision` 문자열의 SHA-256. 큐 snapshot/진단용이며 서버 요청 payload 전체 hash는 아님 |
| `server_sync_queue.source_set_hash` | `report` enqueue 시 source type/local ID/version/hash/relation을 정렬한 줄 단위 문자열의 SHA-256. source가 없거나 다른 entity type이면 NULL |
| `server_sync_queue.payload_json` | 상태·태그처럼 enqueue 시점의 변경 의도를 고정해야 하는 신규 action의 정규화 snapshot. 구 큐의 NULL은 보존 |
| `server_sync_queue.server_conflict_hash_sha256` | 충돌 시 read-only 서버 상세에서 확인한 상대 파일 hash. 로컬 hash, 충돌 원문, 해결 감사와 함께 보존 |
| `documents.server_tags_json` | WPF가 마지막으로 확인한 서버 권위 태그 집합. 다음 태그 큐의 추가/제거 delta 기준이며 로컬 편집 태그와 별도로 보존 |
| `server_id_mappings.server_published_version_id` | 상세 read-back에서 확인한 서버 공개 버전 포인터. 문서·버전 mapping의 revision/hash와 함께 갱신 |

현재 WPF UI의 문서 공개는 서버 승인 작업함에서 직접 처리한다. 공개 API 응답과 상세 read-back이 일치하면 `documents`, `document_versions`, `document_tags`, `server_id_mappings`와 `apply_approval_publication_read_back` 성공 큐 receipt, `activity_history`를 한 로컬 transaction으로 반영한다. transaction이 실패하면 전부 rollback하고, 승인 작업함 새로고침에서 서버의 `PUBLISHED` 승인·공개 포인터·승인 ID를 다시 읽어 복구한다. 로컬 DB의 구 `document_publish/publish_document_version` 큐와 처리 코드는 누적 이력·호환 목적으로 남아 있으며 승인 강제 기본값에서는 승인 ID가 없어 자동 공개할 수 없다. 구 행은 삭제하거나 현재 승인 이력으로 추정해 바꾸지 않는다.

`local_schema_versions`, `server_sync_scopes`, `server_id_mappings.server_epoch`은 아직 구현되지 않은 후속 수렴 모델이다. 현재 복구 binding과 판정 이력은 각각 `server_bindings`, `reconciliation_runs`, `reconciliation_items`에 구현되어 있다.

FastAPI 서버 DB와 WPF 로컬 DB는 이름이 같은 `documents`, `document_versions` 테이블이 있어도 열과 키 계약이 다른 별도 스키마다. WPF `document_versions`는 로컬 `id`를 PK로 사용하고 문서별 `version_no`와 선택적 `server_version_id`를 보존하며, 서버의 `version_id` 열이나 서버 grant FK를 소유하지 않는다. `FLOWNOTE_DATABASE_URL`은 `FLOWNOTE_LOCAL_DATA_DIR` 또는 `FLOWNOTE_LOCAL_DATABASE_PATH`로 결정되는 WPF DB 파일을 가리키면 안 된다.

2026-07-20 보존 복구가 적용된 공통 SQLite에는 다음 두 테이블이 추가로 남는다. 정상 WPF 초기화가 만드는 기능 테이블이 아니라, 잘못 유입된 서버 schema와 원천 row를 삭제 없이 격리한 복구 증거다.

| 테이블 | 역할 |
| --- | --- |
| `preserved_server_controlled_copy_grants` | 잘못 생성된 서버 `controlled_copy_grants`의 원래 열 값과 보존 시각·복구 run ID를 FK 없이 보존 |
| `local_schema_migration_audit` | 복구 migration ID, 원래 DDL, 원천/grant 행 수와 SHA-256, 보호 대상 `document_versions`·`document_access_logs` 행 수와 SHA-256을 보존 |

기존 공통 SQLite에는 FieldComment 명칭 전환 전에 만들어진 호환/잔존 테이블도 남아 있을 수 있다.

| 테이블 | 역할 |
| --- | --- |
| `field_notes` | 구 FieldNote 원천 기록. 새 작업에서는 사용하지 않으며 FieldComment 전환 또는 별도 마이그레이션 검토 대상 |
| `field_note_attachments` | 구 FieldNote 첨부 기록. 새 작업에서는 사용하지 않으며 FieldComment 첨부 전환 또는 별도 마이그레이션 검토 대상 |

2026-07-09 현재 공통 개발 DB `data/local/flownote.local.sqlite`에는 누적 테스트 기록으로 `field_notes` 345건, `field_note_attachments` 20건이 남아 있다. 이 데이터는 테스트 기록 보존 원칙에 따라 삭제하지 않는다. 현재 WPF 동기화 코드는 `server_sync_queue`의 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 항목을 자동 서버 전송 대상에서 제외하고 “구 FieldNote 큐”로 분류한다.

## FastAPI 서버 SQLite

2026-08-15 현재 ORM은 공통 감사 event envelope와 mutation receipt, 문서·FieldComment 검토·보고서·작업순서의 도메인 receipt, 문서 태그 revision snapshot, 서버 복구 reconciliation, AI 질의 legal hold와 민감정보 정책 조작 모델을 포함한 70개 서버 테이블을 생성 기준으로 사용한다. FieldComment 검토 대시보드와 운영 준비도는 새 권위 테이블이나 저장 snapshot을 만들지 않고 현재 도메인 테이블과 감사 anchor를 요청 시점에 집계한다.

서버 기본 DB 경로는 `services/api/data/flownote.sqlite3`이고 테스트 DB 기본 경로는 `services/api/data/flownote.test.sqlite3`이다. 서버 파일은 기본적으로 `services/api/storage/` 아래 저장된다.

서버 ORM 테이블은 다음과 같다.

| 테이블 | 역할 |
| --- | --- |
| `schema_migrations` | 스키마 적용 버전 기록 |
| `server_identity` | singleton 설치 식별자, 복구 epoch, schema contract와 지원 API contract 범위 |
| `reconciliation_runs`, `reconciliation_items` | WPF inventory 대조 run과 항목별 판정·제안 조치·관리자 해결 감사 |
| `user_accounts`, `roles`, `user_roles` | 계정과 역할 기반 권한 |
| `auth_sessions` | access token ID, refresh token hash, 세션 만료/폐기 상태, Android 승인 단말 `device_id` |
| `operator_profiles` | 작업자/작업그룹/대리 입력 주체 |
| `file_objects` | 서버 로컬 파일 참조, MIME, 크기, SHA-256 |
| `documents`, `document_versions` | 문서, 버전, 최신/공개 버전과 공개 승인 근거. 문서와 개별 버전의 재시도 idempotency key를 각각 유일하게 보존 |
| `document_mutation_receipts` | 문서 공개·상태·태그·삭제 mutation key, intent hash, 적용 revision, 최초 성공 응답 |
| `document_approvals` | 정확한 문서 version·revision·file hash, 요청자, 지정 검토자·역할, 상태와 결정·취소·공개 시각을 보존하는 승인 projection |
| `document_approval_events` | 요청·승인·반려·취소·stale·공개·공개 철회 append-only 이력 |
| `document_approval_mutation_receipts` | 검토 요청·결정·취소 mutation key, intent hash와 최초 응답 snapshot |
| `audit_event_envelopes` | 공통 감사 계약. event/actor·role/session·device/target·version·revision/reason/approval/hash/result/server time/run·correlation ID와 도메인 감사 연결을 저장 |
| `sync_mutation_receipts` | 전역 유일 operation key, intent hash, 성공·거부·충돌 결과, HTTP 상태, 공통 event ID와 기존 도메인 receipt 연결을 저장 |
| `tag_definitions`, `document_tags` | 태그 사전과 현재 문서 연결 |
| `document_tag_revisions` | 문서 생성과 태그 mutation 뒤 revision별 태그 집합 JSON. stale 태그 delta의 3-way 병합 기준 |
| `terminal_devices` | Android 현장 단말기 승인 기준 정보 |
| `field_comments`, `field_comment_attachments` | 현장 코멘트와 첨부. 원천 기록과 개별 첨부의 재시도 idempotency key를 각각 유일하게 보존. 담당자, 검토 기한, 마지막 전이 사유, 선정 시각, `review_revision`은 관리자 해석 영역으로 분리 |
| `field_comment_review_mutation_receipts` | 검토 mutation key와 intent hash, comment/revision, 최초 응답 JSON snapshot |
| `comment_templates` | 정형 코멘트 문구 |
| `work_records`, `work_record_versions` | 작업내역 모델 기반 |
| `work_sequence_boards`, `work_sequence_items` | `board_revision`으로 직렬화되는 작업순서 보드와 항목 |
| `work_sequence_change_history` | mutation key와 적용 board revision이 유일하게 연결된 작업순서 변경 이력 |
| `work_sequence_mutation_receipts` | mutation key, intent hash, 결과 revision·change ID·최초 응답 snapshot을 보존하는 작업순서 멱등 receipt |
| `work_sequence_notification_candidates` | 작업순서 알림 후보 |
| `work_sequence_candidate_deliveries` | 후보·채널 조합별 전달 mode, intent hash, 메시지·인수인계·작업순서 원천과 완료/부분 성공 상태 |
| `work_sequence_delivery_recipients` | 후보 전달의 수신자별 성공·실패, handover receipt, 오류와 재시도 횟수 |
| `work_sequence_delivery_templates` | 현장 scope별 작업순서 전달 제목·본문 템플릿과 활성 상태 |
| `notification_channels` | 라인, 설비, 공정, 작업조, 작업내역 단위 업무 채널 |
| `notification_channel_members` | 채널별 사용자 멤버십, 역할, 마지막 읽음 위치 |
| `channel_messages` | 문서, FieldComment, 작업순서, 보고서, 인수인계 원천 이벤트 메시지 |
| `handovers` | 인수인계 원문, 원천·채널 연결, 전체 상태, 생성 멱등키, Android 입력 출처와 승인 단말 ID |
| `handover_receipts` | 수신자별 인수인계 읽음, 확인, 후속조치 필요 상태 |
| `reports`, `report_sources` | 단계형 보고서와 고정 근거 연결. 보고서는 상태, 검토·승인 사용자/시각, `report_revision`, 내용/source 집합 hash, 선택적 생성 문서 ID와 `report_family_id`, 대체 전후 ID·revision·시각, 정정 사유를 보존 |
| `report_mutation_receipts` | 보고서 mutation key와 intent hash, report 계열·revision, 대체 대상 ID·revision, 두 hash, 생성 document/version, 최초 응답 JSON snapshot |
| `ai_search_candidates` | 안정된 candidate ID와 content hash를 가진 AI 자동 조언 전 단계의 근거 검색 후보 read model |
| `ai_search_evaluation_runs` | 외부 AI 없는 ground-truth 회귀 실행과 provider 착수 판단 지표 |
| `ai_search_evaluation_cases` | 질문별 기대/실제 근거, 제외 사유, 순위 hash와 통과 여부 |
| `ai_search_ground_truth_cases` | 고객·현장·라인·DB scope별 사람이 승인한 질문 범주, 정상/제외/상충 유형, 기대/제외 근거, 허용 순위와 시점 기준 |
| `ai_search_ground_truth_provenance` | synthetic/test/anonymous-field/pilot 분류, 실제 현장/스모크 준비도 계열, source snapshot hash와 서로 다른 2인 승인 상태 |
| `ai_provider_onboarding_reviews` | provider/model별 계약·데이터 처리·전송·TLS·장애·비용·kill switch 체크리스트와 기술/보안/법무/고객 착수 결정 |
| `ai_queries`, `ai_query_evidence_candidates`, `ai_query_citations` | 외부 AI 질의 상태와 질의 시점 근거 snapshot, 검증된 주장별 인용 연결 |
| `ai_prompt_versions`, `ai_call_attempts`, `ai_transfer_approvals` | 승인 프롬프트 버전, 정제된 호출 시도 감사, 고객·현장별 외부 전송 승인 |
| `ai_sensitive_data_policies` | 고객·현장별 금칙어·고객 식별자 정책의 불변 원문과 검토·승인·활성 수명주기 |
| `ai_sensitive_data_policy_operations` | 민감정보 정책 작성·상태 변경의 멱등 키와 정제 결과 상태 태그 |
| `ai_operational_policies` | 전역·현장별 kill switch, 요청·동시성·timeout·비용 한도, 보존과 감사 내보내기 정책 |
| `ai_operation_audit_events` | 승인·프롬프트·운영 정책 변경과 호출 전 차단의 정제 감사 이벤트 |
| `ai_retention_audits` | 만료 질의 payload 비식별화와 응답 원문 삭제 결과, 보존 hash 감사 |
| `ai_query_legal_holds` | 질의별 법무·감사 보존 근거와 설정/해제 이력 |
| `document_access_logs` | 서버 문서 접근 로그 |
| `controlled_copy_grants` | SHA-256으로 저장한 1회성 토큰, 사용자·세션·단말·문서 버전, 만료·소비·실패 상태 |
| `android_document_view_grants` | Android 앱 내부 열람용 token hash, 사용자·세션·필수 승인 단말·공개 버전·미디어 종류·크기·SHA-256, 만료·소비·실패 상태 |
| `activity_history` | 서버 활동 이력 |

`audit_event_envelopes`와 `sync_mutation_receipts`는 migration `0002_common_mutation_receipts`에서 additive 방식으로 추가한다. `0003_document_approval_workflow`는 승인 테이블 3개와 `documents.publication_approval_id`, `documents.publication_origin`을 추가한다. `0004_report_correction_lifecycle`은 보고서 계열·대체 열, report receipt의 대체 target, 공통 감사 envelope의 related target을 nullable 열과 인덱스로 추가하고 기존 보고서는 `report_family_id = report_id`로만 보완한다. `0005_work_sequence_candidate_delivery`는 후보의 revision·change ID·만료 시각과 채널별 전달·수신자·템플릿 테이블을 추가하고 기존 후보는 당시 board revision과 연결 가능한 change ID만 보완한다. 기존 보고서/source/document/file/receipt와 작업순서 이력·후보 행은 삭제하지 않는다. 기존 `activity_history`와 도메인 receipt도 이동·수정·백필하지 않으며, 이전 공개본은 승인 근거를 추정하지 않고 `LEGACY_PUBLICATION`으로 둔다. 공통 행이 없는 이전 감사는 조회 시 `이전 형식·일부 필드 없음`으로 표시하고 role·session·revision·result 같은 누락값을 추정하지 않는다.

`sync_mutation_receipts.operation_key`는 서버 전체에서 UNIQUE다. 같은 key·같은 event/target/intent는 최초 성공 또는 거부·충돌 결과로 수렴하고 같은 key의 다른 intent는 `409 IDEMPOTENCY_KEY_REUSED`로 거부한다. 성공 행은 기존 `document_mutation_receipts`, `document_approval_mutation_receipts`, `field_comment_review_mutation_receipts`, `report_mutation_receipts`, `work_sequence_mutation_receipts`의 테이블명과 PK를 연결한다. 업무 변경, 도메인 receipt, 공통 envelope/receipt는 같은 transaction에서 commit한다. 문서 상태, FieldComment 검토, 보고서 상태 전이, 작업순서 항목 상태의 거부·충돌은 업무 transaction을 rollback한 뒤 공통 거부 receipt만 별도 transaction으로 확정하며 업무 row가 바뀌지 않았음을 revision으로 검증한다.

문서 태그 intent의 canonical 문자열은 UTF-8, LF 구분의 `document-tags-v1`, 서버 문서 ID, 10진수 base revision, `add:` 행, `remove:` 행 순서다. 태그 코드는 trim·소문자화·공백 묶음의 `-` 치환 뒤 중복을 제거하고 ordinal 오름차순으로 정렬해 쉼표로 잇는다. SHA-256은 이 문자열의 바이트에 적용한다. base revision 뒤의 모든 aggregate revision에 정확한 `document_tag_revisions` 행이 있을 때만 태그끼리의 경쟁으로 보고 자동 병합한다. 상태·버전·승인·공개·삭제가 만든 revision이 하나라도 섞이면 `TAG_AGGREGATE_CHANGED` 409다.

공개 승인을 취소해 현재 `documents.publication_approval_id`와 일치하던 공개본을 철회하면 문서와 해당 버전은 `WORKING`, 공개 포인터와 공개 flag는 NULL/false가 된다. 공개본을 교체하면 새 공개본의 승인 ID만 문서의 활성 `publication_approval_id`가 되며 이전 승인 projection과 이벤트는 `PUBLISHED` 역사 기록으로 보존한다. 서버에서 문서가 삭제된 뒤 남은 WPF 문서 큐는 모두 `DOCUMENT_DELETED`와 `KEEP_SERVER`만 허용하는 `CONFLICT`로 묶고, 관리자가 사유를 입력해야 `DISCARDED`로 종결한다. 원천 파일·로컬 문서·큐 행은 어느 단계에서도 삭제하지 않는다.

공통 envelope의 필수 필드는 `event_type`, actor ID/role, session ID, target type/ID, result/result code/HTTP status, correlation ID, server time이다. operation key가 있는 mutation은 intent hash와 공통 receipt 연결도 필수다. device ID와 run ID는 요청 세션·헤더에 값이 있을 때만 저장하고 target version/revision·reason·approval·전후 hash는 아래 행위 계약을 따른다.

| 행위 | target version/revision | 사유 | 승인 | 전후 hash |
| --- | --- | --- | --- | --- |
| 문서 상태·삭제·태그 | 문서 revision 필수 | 삭제 필수, 나머지는 현재 API 계약상 선택 | `NOT_REQUIRED` | 성공 필수, 거부·충돌은 선택 |
| 문서 검토 요청·결정·취소·공개 | 문서 revision과 version ID 필수 | 요청·결정·취소는 필수, 공개는 현재 API 계약상 선택 | 요청은 `PENDING`, 승인·공개는 `APPROVED`, 반려·취소·stale은 `REJECTED`와 승인 ID 기록 | 성공 필수, 거부·충돌은 선택 |
| FieldComment 검토 | document version이 있으면 기록, review revision 필수 | 상태 전이 시 필수, 해석 필드만 바꾸면 선택 | 별도 승인 모델이 없어 `NOT_REQUIRED` | 성공 필수, 거부·충돌은 선택 |
| 보고서 상태 전이·정정 대체 | 생성 version이 있으면 기록, report revision 필수. 정정은 related report ID/revision 필수 | 정정 생성은 필수, 일반 전이는 선택 | `REVIEWED`는 `PENDING`/승인자 없음, `APPROVED`·`ARCHIVED`는 `APPROVED`/전이 actor 필수 | 성공 필수, 거부·충돌은 선택 |
| 작업순서 변경 | board revision 필수 | 생성은 서버 고정 사유, 순서·상태는 현재 API 계약상 선택 | 별도 승인 모델이 없어 `NOT_REQUIRED` | 성공 필수, 거부·충돌은 선택 |
| 작업순서 후보 전달 | 후보의 board revision 필수, 관련 change ID는 related target으로 기록 | 전달 사유 필수 | 별도 승인 모델이 없어 `NOT_REQUIRED` | 성공 또는 부분 성공 결과 hash 필수 |

공통 `safe_payload_json`과 실패 응답 snapshot에는 operation key, schema 이름, 정제 코드와 식별자/revision만 저장한다. token, 비밀번호, 고객 문서·FieldComment·보고서 원문, 로컬 절대경로, 불필요한 개인정보는 저장하지 않는다. 전후 상태는 원문 대신 canonical SHA-256으로 기록한다.

통합 변경 이력은 새 테이블이 아니다. `audit_event_envelopes`를 원천으로 `sync_mutation_receipts` 연결 여부와 현재 `documents`, `field_comments`, `reports`, `work_sequence_boards`, `work_sequence_items` 상태를 조회 시점에 결합한다. 따라서 화면용 합계, 위험도, 조치 필요 여부, 영향, 담당자와 다음 행동은 파생 값이며 원천 감사를 수정하지 않고 언제든 다시 만들 수 있다. pagination snapshot은 최초 조회 시점의 event ID 상한만 커서에 보존하고 서버 DB에는 저장하지 않는다.

채널 메시지는 별도 개인 DM이나 개인 메신저 수집이 아니라 업무 채널 멤버십 기준으로 조회된다. 사용자별 알림 목록과 읽음 처리는 `channel_messages`와 `notification_channel_members.last_read_message_id`, `last_read_at`를 함께 사용한다.

`terminal_devices`는 개인 휴대폰 자동 등록 테이블이 아니라 승인된 현장 태블릿 또는 러기드 단말의 운영 기준이다. 단말 용도 `device_mode`는 현장 열람용 `viewer`와 관리 지원용 `admin_support`를 사용한다. 상태는 `ACTIVE`, `INACTIVE`, `RETIRED`이고 폐기 단말은 재활성화하지 않는다. `registered_by`, `updated_by`는 등록자와 마지막 변경자, `replaced_device_id`는 교체 단말이 대체한 기존 단말 ID를 보존한다. Android 앱은 로그인 시 `deviceId`를 보내며, 서버는 같은 ID가 `terminal_devices.device_id`에 있고 `status = ACTIVE`일 때만 세션을 만든다. 성공한 Android 세션은 `auth_sessions.device_id`에 단말 ID를 남기고 로그인 성공 때마다 `terminal_devices.last_seen_at`을 갱신한다. 등록, 정보 변경, 비활성화, 폐기, 교체 이력은 `activity_history`의 `terminal_device.*` 이벤트로 추적한다.

Android 로컬 DB `flownote_android_outbox.db`는 장기 기준 데이터가 아니다. 네트워크 불안정 구간의 FieldComment, 사진 첨부, 신규 인수인계, 받은 인수인계의 확인·보류와 후속 FieldComment 재전송을 위해 `local_id`, `kind`, Keystore AES-GCM 암호문인 `payload`, `idempotency_key`, 새 첨부의 앱 내부 암호화 파일 참조, 서버 원천 ID, 상태, 시도 횟수, 마지막 시도 시각과 암호화한 마지막 오류를 임시 보관한다. 기존 version 1 테이블의 `kind`와 JSON `payload`에 `handover_receipt`, `handover_follow_up` 종류를 추가하므로 Android DB 열을 늘리거나 기존 암호문을 다시 쓰지 않는다. 구 평문 payload와 마지막 오류만 첫 DB open에서 같은 AES-GCM 형식으로 전환하고 기존 암호문은 그대로 읽는다.

새 사진은 선택 즉시 `filesDir/outbox-attachments/`의 AES-GCM 암호문으로 가져오며, 기존 설치에서 남은 persist URI는 전송 완료까지 읽기 호환만 유지한다. 마지막으로 서버가 확인한 활성 채널·수신자 목록도 정규화한 서버 URL+사용자 scope별 AES-GCM 암호문으로 `SharedPreferences`에 보관한다. 받은 인수인계의 작성 중 후속 입력은 서버 URL+사용자+인수인계 scope별 AES-GCM 암호문으로 즉시 저장하고 outbox 보존이 끝난 뒤에만 삭제한다. 선택 캐시는 로그아웃·단말 거부 때 삭제하지만 작성 중 후속 입력과 업무 outbox는 유지한다. 서버는 실제 전송에서 멤버십과 원천을 다시 검사한다. FieldComment, 사진과 인수인계는 각각 `android:{deviceId}:{localId}`, `android-photo:{localId}`, `android:{deviceId}:handover:{localId}` 멱등키를 사용한다. 인수인계 후속 FieldComment는 인수인계 ID·작성자·본문의 SHA-256으로 만든 `handover-follow-up:{digest}`를 쓴다. 코멘트 저장 뒤 채널 알림이 실패하면 같은 outbox row의 서버 `comment_id`를 보존해 다음 시도에서 알림만 보낸다. `PENDING`, `FAILED` 항목은 최대 12회 자동 시도하며 재시도 간격은 시도 횟수에 따라 `15초 → 30초 → 60초`로 증가하고 최대 15분으로 제한한다. 재전송 성공 후 서버 원천 ID를 연결하고 `SYNCED`로 전환하며 서버 저장을 확인한 암호화 사진 파일을 정리한다. `SYNCED` 항목과 최대 시도 횟수에 도달한 항목은 자동 재전송하지 않는다.

Android 로컬 DB `flownote_android_notifications.db`는 표시한 알림의 공개 `message_id`, 정수 cursor와 처리 시각을 `(server_user_scope, message_id)` 유일키로 보존한다. 이 원장은 서버 업무 원문이 아니라 cursor 재조회 때 같은 시스템 알림을 다시 표시하지 않기 위한 로컬 멱등 기록이다. 사용자별 cursor는 기존처럼 `SharedPreferences`에 유지하며, 알림 표시와 원장 기록이 끝난 뒤 cursor를 전진시킨다.

서버의 `documents`, `document_versions`, `field_comments`, `field_comment_attachments`, `document_access_logs`, `reports`, `handovers`는 각 생성 단위의 선택적 `idempotency_key`를 최대 160자로 저장하고 유일 인덱스로 보호한다. Android 인수인계에는 이 키가 필수다. 앱 시작 시 기존 SQLite에도 누락된 열과 유일 인덱스를 보완하며 기존 `handovers`에는 `entry_source = field_user`, 선택 `device_id`를 additive migration으로 추가한다. 동일 키 재요청은 같은 부모 원천과 같은 요청일 때 기존 row를 반환하고, 다른 요청에 사용된 키는 충돌로 거부해 인수인계·채널 메시지·수신자 receipt와 첨부 중복을 막는다.

`field_comments`의 원천 핵심 필드는 생성 후 ORM 수준에서 불변이며, 원천 row 자체의 ORM 삭제도 거부한다. 관리자 영역은 `assigned_to`, `review_due_at`, `review_revision`, `conflict_flag`, `conflict_basis`, 정리·분석·결정 사유를 별도로 가진다. 논리 `ASSIGNED`는 기존 DB 제약을 바꾸지 않고 `status = NEW AND assigned_to IS NOT NULL`로 표현한다. 관리자 대리 입력은 인증 입력자, `reported_by`, `operator_id`를 분리해 `field_comment.proxy_created` 감사에 보존한다.

보고서 `FIELD_COMMENT` source는 `SELECTED` 상태만 저장하며 `source_version_id`에 관찰 문서 버전, `source_revision`에 선정 시점 `review_revision`, `source_hash_sha256`에 원천 hash를 고정한다. 최초 source 집합은 distinct source type 2종 이상을 요구한다. 일반 보고서는 `DRAFT` 또는 `AI_DRAFTED`에서 `REVIEWED`나 `APPROVED`로, `REVIEWED`에서 `APPROVED`로, `APPROVED`에서 `ARCHIVED`로 전이한다. 정정본만 내용 변경에 따른 재검토를 위해 `REVIEWED → DRAFT → REVIEWED`를 허용한다. 검토 이후에는 source를 교체하지 않으며 각 전이와 최종 파일 생성 직전에 상태·version·revision·hash·채널 권한을 재검증하고 변경 시 409로 중단한다. 최종 보고서 본문에도 type/ID/version/revision/trace/hash를 기록해 `generated DocumentVersion → ReportSource → FieldComment → attachment/document version` 역추적을 유지한다.

정정본은 새 `reports` 행과 새 `report_sources` snapshot으로 만든다. `report_family_id`는 최초 보고서 ID, `replaces_report_id`와 `replaces_report_revision`은 정정 기준 확정본, `correction_reason`은 필수 변경 사유다. 같은 `replaces_report_id`는 한 정정본만 참조할 수 있다. 정정 생성 시 기본값은 기준 보고서의 전체 source snapshot 복사이며, 선택한 새 source 전체 집합을 요청하면 그 집합으로 새 snapshot을 고정한다. 두 경우 모두 생성 직전 현재 version/revision/hash와 채널 권한을 재검사하고 자동 제외하지 않는다.

정정본이 `DRAFT` 또는 `REVIEWED`인 동안 기준 `APPROVED` 보고서가 현재 유효본이다. 정정 승인 transaction은 새 보고서·새 `IN_REVIEW` 생성 문서·receipt·감사와 기준 보고서의 `superseded_by_report_id`, `superseded_at`, revision 증가를 함께 확정한다. DB의 기존 `status = APPROVED` 제약과 과거 row를 재작성하지 않기 위해 대체된 보고서의 읽기 상태는 `superseded_by_report_id IS NOT NULL`일 때 논리 `SUPERSEDED`로 투영한다. 이전 생성 문서는 삭제하지 않고 `ARCHIVED`로 전환해 공개 포인터를 해제하며, 새 생성 문서는 자동 공개하지 않고 exact-version 공개 승인을 다시 받는다. 계열에서 `status = APPROVED AND superseded_by_report_id IS NULL`인 보고서만 현재 유효본이다.

WPF 로컬 `report_sources`도 `source_version_id`, `source_revision`, `source_hash_sha256`, `snapshot_verified`를 저장한다. 서버 초안 생성 때 검증해 고정한 source만 `snapshot_verified = 1`로 기록하며, 동기화 큐의 source 집합 hash에도 이 네 값을 포함한다. 최종 서버 저장에 실패하거나 원천 재검증에서 충돌해도 로컬 보고서와 source row를 삭제하지 않는다. 재시도 요청은 같은 고정 revision/hash와 mutation key를 사용하고, 검증하지 못한 구 row는 기존 값과 이력을 지운 채 보정하지 않는다.

`controlled_copy_grants`는 원본 토큰 대신 `token_hash`만 저장한다. 각 grant는 공개 문서와 정확한 공개 버전, 요청 사용자, `auth_sessions.session_id`, 선택적 승인 단말 ID, 발급 시점의 파일 크기와 SHA-256에 묶인다. 상태는 `ISSUED`, `CONSUMED`, `EXPIRED`, `FAILED`이며 기본 60초(설정값은 5~300초로 정규화) 안에 한 번만 소비할 수 있다. 스트리밍 시작 전 상태를 원자적으로 `CONSUMED`로 바꾸고, 이후 공개 상태·저장 경로·크기·SHA-256 검사가 실패하면 `FAILED`와 정제된 실패 사유를 남긴다.

`android_document_view_grants`도 원본 token을 저장하지 않고 SHA-256 hash만 보존한다. controlled copy와 달리 `device_id`가 필수이며 `media_kind`, 정규화 MIME type, 발급 시 파일 크기와 SHA-256을 고정한다. 상태는 `ISSUED`, `CONSUMED`, `EXPIRED`, `FAILED`이고 1회 스트림 시작 전에 원자적으로 소비한다. `document_access_logs`와 `activity_history`에는 grant 발급, 스트림 시작·완료, 실패·차단·만료를 사용자·단말·문서 버전과 함께 남긴다. Android 내부 난수 캐시 파일은 서버 기준 데이터가 아니며 DB 모델로 관리하지 않는다.

보고서 서버 저장 실패는 WPF 전용 큐를 새로 만들지 않고 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남긴다. 큐는 한글 실패 사유, `last_attempt_at`, `attempt_count`를 기존 동기화 항목과 같은 방식으로 기록한다. 신규 report 큐는 enqueue 시 source 집합 hash를 저장하고 안정된 `idempotency_key`를 `idempotencyKey`와 `mutationKey` 양쪽에 사용한다. 성공 응답 source를 정규화해 source-set hash를 대조한 뒤 report revision과 두 hash를 로컬 문서에 보존한다. FieldComment 검토 구 큐처럼 `base_domain_revision`이 NULL인 항목은 서버 상세 조회에서 얻은 현재 `review_revision`을 PATCH 기준값으로 사용한다.

로컬 보고서 문서는 `documents.document_type = Report`인 문서이며, 선택한 근거는 로컬 `report_sources.local_report_document_id`로 연결한다. 재시도 성공 시 `documents.server_report_id`, `documents.server_document_id`, 최신 `document_versions.server_version_id`, `server_id_mappings(entity_type IN ('report', 'document', 'document_version'))`를 채운다.

## Schema version과 클라이언트·서버 호환 정책

현재 서버는 `schema_migrations`에 `0001_initial_mvp_schema`를 기록하고 WPF는 `CREATE TABLE IF NOT EXISTS`와 `EnsureColumn`을 사용한다. 수렴 계약 도입 뒤에는 이 방식을 아래 공통 정책으로 일반화한다.

- local/server schema version은 단조 증가 정수와 고유 migration ID를 함께 쓴다. 앱 build 번호나 파일 생성 시각을 schema version으로 사용하지 않는다.
- migration은 기본적으로 새 nullable 열, 기본값이 있는 열, 새 테이블·인덱스를 추가하는 additive 방식이다. rename, type 변경, NOT NULL 강화와 테이블 재작성은 별도 expand/backfill/verify/contract 단계와 직전 DB backup이 필요하다.
- 앱은 지원하는 `minLocalSchema..maxLocalSchema`, `minServerSchema..maxServerSchema`, `apiContractVersion`을 가진다. DB가 최소보다 낮으면 순서대로 migration하고 최대보다 높으면 쓰기를 거부한다. 서버 API 범위가 맞지 않으면 로컬 저장은 허용하되 server sync와 서버 직접 작업순서 mutation은 중지한다.
- 서버는 자신의 `minClientContract..maxClientContract`를 manifest로 반환한다. 교집합이 없으면 426 `CLIENT_CONTRACT_UNSUPPORTED`, schema migration 중이면 503 `SCHEMA_MIGRATION_IN_PROGRESS`를 반환한다.
- 각 migration은 한 transaction 안에서 적용하고 migration row를 마지막에 기록한다. 시작 전후 `PRAGMA quick_check`, `PRAGMA foreign_key_check`, 도메인별 count/hash, 중복 key와 orphan source 검사를 남긴다. 실패하면 transaction을 rollback하고 원본 DB·backup·실패 로그를 보존한다.
- WPF migration의 보호 집합은 모든 로컬 원천 파일 참조, `field_comments`, 첨부, 보고서와 `report_sources`, 작업순서·이력, `server_sync_queue` 전 상태, `server_id_mappings`, 알림 cursor/message다. 특히 `FAILED`/`CONFLICT`/`DISCARDED` 큐도 count와 row hash가 같아야 한다.
- server migration의 보호 집합은 문서/버전/file object, FieldComment/첨부, 보고서/source, 작업순서/이력, mutation receipt와 접근 로그다. 공개 포인터 orphan, report source orphan, 동일 idempotency key 중복은 0건이어야 한다.

migration 전후 원천 hash는 테이블마다 안정 PK 순으로 정렬한 핵심 열의 canonical JSON과 파일 SHA-256을 사용한다. 새 nullable/default 열 때문에 전체 row byte 표현이 달라질 수 있으므로 기존 핵심 열 projection의 hash를 비교한다. 구 DB를 신규 DB로 올린 뒤 보호 원천 count/hash, 보존 FAILED 큐 count/hash가 하나라도 달라지면 호환 완료로 판정하지 않는다.

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

`ai_search_ground_truth_cases`는 고객·현장·선택적 라인과 로컬 경로를 노출하지 않는 DB fingerprint scope에 묶인다. 질문 범주는 안전, 품질, 설비 이상, 작업 보류, 재작업, 인수인계, 최신 공개 문서, 상충 기록이고 각 범주에서 `NORMAL`, `EXCLUSION`, `CONFLICT`를 구분한다. 기대 포함 근거는 승인 시점의 candidate/source/version/trace ID와 content hash, 승인자의 열람 권한, `as_of` 이전 존재를 검증한 뒤 근거 설명과 함께 snapshot으로 고정한다. 제외 근거도 실제 원천 row, content hash, 제외 사유와 설명으로 역추적되어야 한다. 허용 순위 최소·최대, `as_of`, 승인자·승인 시각을 보존하며 승인 질문 원본을 평가 실행과 분리한다.

`ai_search_ground_truth_provenance`는 질문과 1:1이며 `SYNTHETIC`, `TEST`, `ANONYMOUS_FIELD`, `PILOT` 분류를 가진다. 앞의 두 분류는 `SMOKE_REGRESSION`, 뒤의 두 분류는 `FIELD_READINESS`로 고정한다. source snapshot hash, 비민감 여부와 설명, 서로 다른 첫/두 번째 승인자와 시각을 보존한다. 첫 승인 상태는 `PENDING_SECOND_APPROVAL`이며 독립 두 번째 승인 뒤 `APPROVED`가 되어야 질문이 활성화된다. 실제 현장 준비도와 스모크 회귀 준비도는 별도 집계한다. 승인 `FIELD_READINESS` dataset과 provider 착수 48건에는 고객 승인을 받은 `ANONYMOUS_FIELD`만 포함하고 `PILOT`은 별도 이력으로 보존한다.

`smoke48-v1` 회귀 matrix의 업무 원천은 case와 별도 row로 보존한다. 범주마다 `NORMAL` 2건, `EXCLUSION` 2건, `CONFLICT` 2건을 배정하고 FieldComment는 고정 `idempotency_key`로 재사용한다. 상태는 승인 전이 규칙에 따라 `ANALYZED`, `REVIEWED`, `SELECTED`, `EXCLUDED`로 수렴하며 `assigned_to`, `review_due_at`, `last_transition_reason`, `review_revision`을 필수 증거로 본다. `activity_history`의 검토 변경 before/after에는 동일한 원천 SHA-256이 있어야 하며 상태 정제 중 `raw_content`와 source 연결은 바뀌지 않는다.

회귀 보고서는 범주·variant별 1건이고 `report_sources`에 `DOCUMENT`, `FIELD_COMMENT`, `WORK_SEQUENCE_HISTORY`를 연결한다. 각 source는 원천 ID, 고정 version ID, 저장 시점 source SHA-256, 독립 trace ID를 가진다. 최소 두 source type 규칙은 DB 검증에서도 다시 확인한다. 문서 연결은 `document_tags`/`tag_definitions`를 사용해 `equipment`, `item`, `process`, `error_type` 중 최소 두 축을 요구하지만 고객 문서 트리나 BOM 계층을 생성하지 않는다.

준비도 산출 시 `ai_search_ground_truth_cases`와 provenance를 join한 뒤 `approval_status = 'APPROVED'`이고 활성인 행만 사용한다. 최상위 `ground_truth_count`, 범주×유형 coverage, 승인 dataset과 평가 run은 `readiness_track = 'FIELD_READINESS'`만 집계한다. `SMOKE_REGRESSION`은 별도 count/coverage/evaluation 필드에만 집계한다. 두 계열을 `UNION ALL`, 조건 없는 `COUNT(*)`, 합산 DTO로 provider 착수 값에 넣는 것은 금지한다. 기준 구현은 `app/services/ai_readiness.py::scope_readiness`, API는 `GET /api/v1/ai-search/readiness`, SQL 회귀는 `scripts/sql/verify-ai-ground-truth-48.sql`이다.

`ai_ground_truth_dataset_versions`는 승인 사례 집합의 운영 version이다. `dataset_key + version`, scope, 준비도 계열, 작성자, 검토자, 서로 다른 두 승인자, 전체 snapshot hash, 변경 사유와 `replaces_dataset_version_id`를 보존한다. 상태는 `DRAFT`, `IN_REVIEW`, `PENDING_FIRST_APPROVAL`, `PENDING_SECOND_APPROVAL`, `APPROVED`, `SUPERSEDED`, `RETIRED`다. DB check constraint도 검토자와 작성자, 1차 승인자와 작성자·검토자, 2차 승인자와 작성자·검토자·1차 승인자가 서로 다르도록 강제한다. `APPROVED` 이후에는 row와 구성원을 수정하지 않고 새 version을 만든다. 대체 대상은 같은 고객·현장·DB·라인·준비도 계열 및 같은 dataset key의 불변 version으로 제한하고, ID 기반 상세·변경·전이는 현재 고객·현장·DB scope 안에서만 찾는다.

`ai_ground_truth_dataset_cases`는 dataset version과 사례의 다대다 구성 snapshot이다. version 안에서 사례 ID와 case key는 각각 유일하며, 구성 시 사례 본문·범주/유형·포함/제외 근거·허용 순위·`as_of`의 hash를 저장한다. 최종 승인 시 현재 사례 hash와 다시 비교한다. `ai_evaluation_dataset_bindings`는 평가 `run_id`를 정확한 `dataset_version_id`와 dataset snapshot hash에 1:1로 결합한다. 따라서 준비도 판정과 과거 run 조회는 최신 사례 집합을 추정하지 않고 당시 승인본으로 재현한다.

`ai_field_readiness_sample_reviews`는 승인된 실제 익명 현장 dataset snapshot과 48건 평가 run에 묶인 사람 표본 검토다. 독립 검토는 24개 범주·유형 칸마다 1건씩 같은 표본을 사용하며 표본 계획 참조·case key 집합·sample hash와 인용 trace/의미, 상충 표시, 권한 경계 판정을 보존한다. 같은 run에서 같은 사용자의 중복 검토를 막고 독립 검토자는 서로 달라야 한다. 두 decision hash가 다르면 제3 사용자의 `CONSENSUS` row가 앞선 review pair를 연결해야 완료된다. 원래 두 row와 불일치 판정은 수정하거나 삭제하지 않는다.

`ai_search_evaluation_runs`는 실행 ID/라벨, 요청자와 평가 대상 사용자, ID/hash·순위 안정성, scope, precision@k, recall@k/top-k 포함률, 제외 원천 노출, 권한 누출, 존재하지 않는 인용, citation trace·의미 일치, 상충 표시율과 provider 착수 가능 지표를 보존한다. `ai_search_evaluation_cases`는 질문, 기대/실제 `SUFFICIENT` 또는 `INSUFFICIENT_EVIDENCE`, 기대 근거 JSON, 실제 candidate/source/version/trace/content hash snapshot, 제외 근거와 사유, ranking hash를 보존한다. 테스트와 사람형 스모크의 회귀 기록이므로 자동 삭제하지 않는다.

`ai_provider_onboarding_reviews`는 고객·현장·provider·model·review version을 유일하게 묶는다. 체크리스트 JSON은 계약 조건, provider 보존 기간, 학습 사용 여부, 전송/처리 지역, TLS, timeout, 429, 5xx, 비용 한도, kill switch, 법무 승인, 고객 승인을 각각 `PENDING`/`PASS`/`FAIL`과 근거 참조로 보존한다. 기술·보안·법무·고객 상태는 `PENDING`/`APPROVED`/`REJECTED`, 검토자와 시각을 별도로 기록한다. 새 심사는 기존 row를 덮어쓰지 않고 새 version을 만들며 체크리스트 전건 `PASS`와 네 영역 `APPROVED`가 함께 있어야 착수 승인이다.

`ai_sensitive_data_policies`는 `DRAFT → REVIEWED → APPROVED → ACTIVE`로 전이한다. 작성자와 검토자는 달라야 하고 승인자는 두 사람 모두와 달라야 한다. 활성 정책을 새 승인 버전으로 대체하면 이전 정책은 `SUPERSEDED`, 승인 철회는 `APPROVAL_WITHDRAWN`, 폐기는 `RETIRED`가 되며 원문을 수정해 되살리지 않고 새 버전을 만든다. 활성 정책은 고객·현장당 하나이며 provider 경계는 정책 ID·content hash·`state_revision` snapshot을 호출 직전과 응답 직후 다시 비교한다. 철회·폐기 또는 snapshot 변경은 신규 호출을 차단하거나 이미 생성된 응답을 폐기한다.

품질 점검은 후보 수와 제외 사유를 함께 산출한다. `REPORT_SOURCE`의 `DOCUMENT` 원천은 `documents.status != DELETED`와 `documents.deleted_at IS NULL`을 모두 만족해야 하며, 버전 ID가 있으면 그 버전이 같은 문서에 속하는지도 확인한다. 조건을 만족하지 않으면 `report_source_missing_origin`으로 집계한다. FieldComment 검토 품질은 전체 상태별 개수, `ANALYZED`/`REVIEWED`/`SELECTED` 합계, AI 착수 최소 기준 100건 대비 부족분을 표시한다. FieldComment가 대부분 `NEW`라면 검색 후보에는 들어갈 수 있어도 요약 신뢰도와 AI 착수 기준은 부족한 것으로 본다.

MES/ERP 어댑터는 후속 범위이므로 검색 후보 생성은 `work_records.external_system`, `external_ref_id` 같은 외부 연동 필드를 사용하지 않는다. `mes_integration` 입력으로 들어온 FieldComment도 어댑터 정책이 정해지기 전에는 후보에서 제외한다.

## 외부 AI 질의와 호출 로그 안전장치

다음 모델은 외부 AI 1단계의 안전장치와 감사 골격으로 구현되었다. provider 중립 fake/recording adapter와 제한형 JSON 네트워크 adapter가 있으며, 네트워크 adapter는 `test` 환경의 별도 명시 설정에서만 생성된다. 기본 `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`와 `FLOWNOTE_AI_PROVIDER_ADAPTER_MODE=DISABLED`는 모든 외부 호출 시도를 차단한다. 기존 `ai_search_candidates`는 외부 AI 설정과 무관하게 재생성 가능한 read model로 유지한다.

| 테이블 | 주요 필드 | 역할과 보존 기준 |
| --- | --- | --- |
| `ai_queries` | 기존 질의/scope/보존 필드, `immediate_expiry_operation_key`, `immediate_expiry_requested_at`, `immediate_expiry_reason` | 질의, 호출 사용자, 고객·현장 scope, 처리 상태와 응답 저장 여부의 기준 row. 단일 즉시 만료의 안정 operation key·요청 시각·사유를 보존해 응답 유실 재시도가 같은 결과를 읽고 다른 사유의 key 재사용이나 새 감사 생성을 막는다. 만료 시 payload를 `[EXPIRED]`로 비식별화하고 저장 응답 원문을 삭제한다. |
| `ai_query_evidence_candidates` | `id`, `query_id`, `candidate_id`, `source_type`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `rank`, `selected_for_prompt`, `sent_externally`, `content_hash`, `eligibility_result`, `exclusion_reason` | 질의 시점의 적격·제외 후보 ID와 순위, provider 경계 전달 여부, 원천 식별자와 content hash snapshot. 제외 후보도 원문 없이 `EXCLUDED`와 `SOURCE_FORBIDDEN`/`CONTENT_RESTRICTED` 사유를 남기며 provider DTO에는 포함하지 않는다. |
| `ai_query_citations` | `citation_id`, `query_id`, `claim_key`, `candidate_id`, `source_type`, `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`, `internal_source_uri`, `content_hash`, `validated_at` | 반환한 각 사실 주장과 문서 버전, FieldComment, 작업순서 이력 또는 `report_sources.id`의 연결. 1년 보존은 후속 운영 정책이다. |
| `ai_query_legal_holds` | 기존 설정/해제 필드, `operation_key`, `release_operation_key` | 법무·감사 보존 명령. query별 활성 row는 하나만 허용하고 설정/해제 operation key도 각각 유일하다. `ACTIVE`인 동안 payload 만료를 중지하며 `RELEASED` 전이는 원래 설정·근거 번호·해제 근거를 같은 row에 보존하고 삭제하지 않는다. |
| `ai_prompt_versions` | `prompt_version_id`, `name`, `version`, `template_hash`, `template_text`, `allowed_purpose`, `created_by`, `approved_by`, `approved_at`, `retired_at` | 재현 가능한 불변 프롬프트 버전. 승인 후 내용을 덮어쓰지 않고 새 버전을 만든다. |
| `ai_call_attempts` | `attempt_id`, `query_id`, `provider`, `model`, `provider_request_id`, `status`, `started_at`, `finished_at`, `http_status`, `error_code`, `sanitized_error_message`, `input_units`, `output_units` | 최초 호출과 timeout/429/5xx 재시도를 요청 ID에 연결하는 호출 및 오류 로그. 일반 로그에는 원문 프롬프트, 근거 본문, 응답, 자격증명이나 provider raw body를 넣지 않고 정제한 메타데이터를 남긴다. 1년 보존은 후속 운영 정책이다. |
| `ai_transfer_approvals` | `approval_id`, `customer_scope`, `site_scope`, `provider`, `model_scope`, `allowed_source_types`, `data_handling_policy_version`, `approved_by`, `approved_at`, `expires_at`, `revoked_at`, `reason` | 고객·현장별 외부 전송 승인. 만료·철회 시 새 호출을 즉시 차단하며 `admin` 또는 `system-admin`의 승인 주체와 근거를 보존한다. |
| `ai_sensitive_data_policies` | `policy_id`, `customer_scope`, `site_scope`, `version`, `forbidden_terms_json`, `customer_identifiers_json`, `content_hash`, `status`, `is_active`, `state_revision`, 작성/검토/승인/활성/철회/폐기 사용자·시각, `replaced_by_policy_id`, `created_at`, `updated_at` | 고객·현장별 사용자 정의 금칙어와 고객 식별자 정책. 원문은 생성 뒤 불변이며 API에는 content hash와 항목 수만 반환한다. |
| `ai_sensitive_data_policy_operations` | `operation_id`, `operation_key`, `policy_id`, `action`, `request_hash`, `result_state_tag`, `created_by`, `created_at` | 작성·검토·승인·활성화·대체·승인 철회·폐기의 멱등 receipt. 같은 key와 같은 요청은 기존 정책을 read-back하고 다른 요청의 key 재사용은 충돌 처리한다. |

`response_storage_mode`는 `DO_NOT_STORE`, `STORE_90_DAYS`만 허용한다. 기본값은 `DO_NOT_STORE`이며 이때 응답 본문은 요청 세션에 반환한 뒤 저장하지 않는다. `STORE_90_DAYS`는 본문과 별도 `response_retention_until`을 저장한다. 서버 lifespan 스케줄러와 `system-admin` 일괄/단일 즉시 실행 API는 만료된 질의 문구를 `[EXPIRED]`로 비식별화하고 저장 응답 원문을 삭제하되 query/response hash, 근거·인용·호출 메타데이터와 `ai_retention_audits`를 보존한다. 단일 만료가 만든 retention audit에는 같은 `operation_key`를 유일하게 연결한다. 같은 `query_id`의 `ai_query_legal_holds.status = ACTIVE`이면 정기·수동 일괄·단일의 세 만료 경로가 모두 건너뛴다. hold 해제는 `RELEASED` 상태와 해제자·시각·사유를 누적하고 row를 삭제하지 않는다. 질의 상세 `stateTag`는 원문 만료 여부, 응답 보존 여부, 두 보존 시각과 활성 hold ID를 결합한 낙관적 동시성 표식이며 DB 원문을 노출하지 않는다.

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

`documents.revision`은 서버가 단독으로 증가시키는 문서 aggregate revision이다. 최초 등록은 1이며 새 버전, 문서 상태, 버전 상태, 공개본 교체, 태그 병합, soft delete처럼 서버 기준 상태가 실제로 바뀔 때 한 번 증가한다. WPF의 로컬 `version_no`나 수정 시각으로 대체하지 않는다. WPF는 마지막 서버 read-back 값을 `documents.server_revision`, `documents.server_version_id`, `documents.server_published_version_id`, `documents.server_tags_json`에 보관하고 큐 생성 시 기준값을 복사한다.

문서 상태 전이는 `WORKING → IN_REVIEW|ARCHIVED`, `IN_REVIEW → WORKING|ARCHIVED`, `PUBLISHED → IN_REVIEW|ARCHIVED`, `ARCHIVED → WORKING|IN_REVIEW`만 상태 API에서 허용한다. `PUBLISHED` 진입은 publish API만 수행한다. `DELETE /api/v1/documents/{document_id}`는 `DELETED`, `deleted_at`, 공개 포인터 해제를 같은 revision 변경으로 처리하며 삭제된 서버 문서는 로컬 재전송으로 암묵 복구하지 않는다.

서버 문서 버전 상태:

- `WORKING`
- `IN_REVIEW`
- `APPROVED`
- `PUBLISHED`
- `SUPERSEDED`
- `ARCHIVED`

FieldComment 상태:

- `NEW`
- `ASSIGNED` (API·감사·화면의 논리 상태. SQLite에는 `NEW`와 `assigned_to` 조합으로 저장)
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

새 상태가 `HOLD`이면 `work_sequence_items.hold_reason`에 공백이 아닌 사유가 저장되어야 한다. API는 `holdReason`을 우선 사용하고 없으면 같은 요청의 `changeReason`을 보류 사유로 사용하며, 둘 다 비어 있으면 revision을 올리지 않고 요청을 거부한다.

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

`PENDING`은 전송 가능 또는 선행 조건 대기, `FAILED`는 원인을 해결한 뒤 같은 key로 재시도 가능하거나 로컬 원천 오류로 보존 중, `CONFLICT`는 관리자 판정 전 자동 재시도 금지다. `SYNCED`와 `DISCARDED`만 종결 상태다. `DISCARDED`는 서버본 유지 사유가 있는 감사 종결이며 삭제를 뜻하지 않는다.

`server_sync_queue`는 문서 작업에서 `base_server_revision`, `expected_server_version_id`, `expected_published_version_id`, `local_file_hash_sha256`를 생성 시점 snapshot으로 보존한다. 태그 `payload_json`은 `BaseRevision`, `AddedTags`, `RemovedTags`, `IntentHash`, `DesiredTags`와 기준 태그 확인 여부를 저장한다. 문서가 아직 서버에 등록되지 않았다면 최초 등록 응답의 revision·태그 집합으로 delta를 한 번 확정하고 같은 큐 row에 보존한 뒤 전송한다. 이미 매핑된 문서인데 `server_tags_json`이 없는 구 큐는 현재 서버값을 기준값으로 추정하지 않고 `LEGACY_BASE_MISSING` 충돌로 남긴다. 일반 상태와 FieldComment 검토도 enqueue 시점 상태/내용을 `payload_json`에 고정해 여러 오프라인 변경이 마지막 로컬 값으로 뭉개지지 않게 한다. `base_domain_revision`은 FieldComment 검토 기준 revision, `intent_hash`는 일반 큐의 진단 hash이자 태그 큐에서는 서버가 검증하는 canonical 의도 hash, `source_set_hash`는 보고서 근거 집합 hash다. 409와 read-back 불일치는 일반 전송 실패와 분리해 `CONFLICT`, `conflict_code`, 로컬/서버 hash, 원 응답을 기록한다. 관리자 해결 뒤 로컬 요청을 최신 서버 revision에서 다시 보내면 태그 payload의 base와 intent hash도 명시적으로 다시 계산하고 `resolution_action = RETRY_LOCAL_ON_LATEST`를 남긴다. 서버본 유지로 폐기하면 `DISCARDED`와 `KEEP_SERVER`를 사용한다. 두 경로 모두 사유, 해결자, 해결 시각과 `activity_history` 감사를 남기며 앱 재시작 뒤에도 유지한다.

서버 scope 상태는 `ACTIVE`, `RECONCILIATION_REQUIRED`를 사용한다. reconciliation item 결과는 `CONFIRMED`, `ABSENT`, `DIVERGED`, 로컬 적용 결과는 각각 `REBOUND`, `REQUEUE`, `CONFLICT`를 사용한다. 승인 뒤 `resolution_status`는 `REBOUND_CONFIRMED`, `REQUEUED_FOR_RETRY`, `APPROVED_CONFLICT`다. DIVERGED 항목은 local/server hash, 사유, 승인자, 해결 시각을 유지하며 자동 덮어쓰지 않는다. reconciliation run은 `REVIEW_REQUIRED`, `APPLIED`, `FAILED`이며 실패 run과 item은 삭제하지 않는다.

문서·공개 버전 불변조건:

- `documents.latest_version_id`는 같은 문서에서 유일하게 `is_latest = true`인 버전을 가리키고 버전 번호는 감소하지 않는다.
- `documents.status = PUBLISHED`이면 `published_version_id`는 null이 아니며 같은 문서의 `version_status = PUBLISHED`, `is_published = true`인 정확히 한 버전을 가리킨다.
- publish 전에 서버 저장 파일을 다시 읽어 `file_objects.hash_sha256`과 비교한다. 불일치나 파일 누락은 `FILE_HASH_MISMATCH` 충돌이며 공개 포인터를 바꾸지 않는다.
- 같은 idempotency key의 동일 내용 재시도는 기존 결과를 반환한다. 파일 hash나 핵심 메타데이터가 다르면 `IDEMPOTENCY_KEY_REUSED`로 거부한다.
- 공개·문서 상태·태그는 같은 mutation key와 intent를 `document_mutation_receipts`에서 재생한다. WPF read-back이 상태·공개 포인터·태그와 revision을 확인하기 전에는 `SYNCED`가 아니다.
- 태그만 기준 revision 이후의 비경합 추가·제거를 자동 병합한다. 같은 태그의 반대 방향 변경과 비활성·삭제 태그는 구조화된 409로 남기며, 파일·version hash·상태·공개 포인터·삭제는 태그 병합에 포함하지 않는다.
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
- `SUPERSEDED`(읽기 projection. 저장 기준은 `superseded_by_report_id IS NOT NULL`)

서버 인증 세션 상태:

- `ACTIVE`
- `REVOKED`
- `EXPIRED`

## 작업순서 후보 전달 모델

`work_sequence_notification_candidates`는 후보가 만들어진 `board_revision`, 직접 원천인 `change_id`, 생성 후 24시간인 `expires_at`을 보존한다. 이후 작업판 revision이 바뀌면 기존 후보를 새 상태의 알림으로 해석하지 않고 stale 충돌로 막는다.

`work_sequence_candidate_deliveries`는 `candidate_id + channel_id` 유일 제약으로 한 후보의 채널별 전달 의도를 불변으로 보존한다. 한 후보는 채널마다 독립 row를 가질 수 있다. row에는 멱등키와 intent hash, 전달 당시 board revision·change ID, `CHANNEL|HANDOVER`, 제목·본문·사유, 작업순서 source, 관련 공개 문서·버전, 요청 수신자 snapshot, message·handover ID, `PARTIAL|COMPLETED` 상태가 남는다. 기존 candidate row를 덮어써 다중 채널 이력을 잃지 않는다.

`work_sequence_delivery_recipients`는 delivery와 수신자 조합별 유일 receipt다. `DELIVERED|FAILED`, 선택적 handover receipt ID, 실패 코드·안내와 시도 횟수를 보존한다. 부분 성공 재시도는 `FAILED` row만 갱신하며 성공 row와 공개 ID를 바꾸지 않는다. candidate `SENT`는 하나 이상의 delivery가 `COMPLETED`일 때의 projection이다. 일부 실패만 있는 delivery는 `PARTIAL`, 함께 만든 handover는 `FOLLOW_UP_REQUIRED`, candidate는 `CANDIDATE`를 유지한다.

`work_sequence_delivery_templates`는 서버 인증의 `site_scope + name`으로 유일한 현장별 문구다. 제품 공통 기본 문구는 저장하지 않는다. 작업순서 쓰기 role이 만들 수 있고 같은 현장의 작성자 또는 `admin`·`system-admin`만 수정·보관한다.

`channel_messages`와 `handovers`의 `related_document_id`, `related_document_version_id`는 작업순서 원천과 별개로 현재 공개 문서 이동 정보를 제공한다. `CHANNEL` 메시지와 인수인계 원문이 작업순서 항목을 원천으로 삼을 때는 `source_id = item_id`, `source_version_id = change_id`로 고정하고 delivery receipt에도 같은 `change_id`를 남긴다. `HANDOVER` 채널 메시지는 `source_type = HANDOVER`, `source_id = handover_id`로 인수인계를 가리키면서 `source_version_id = change_id`를 유지한다. 따라서 문서 연결이 바뀌어도 전달 당시 작업 항목과 변경 근거가 사라지지 않는다.

## 외부 AI 운영·보존 모델

- `ai_transfer_approvals`: 고객/현장/provider/model/목적/source type, 처리정책 버전, 승인·만료·폐기 시각을 보존한다. 다른 고객/현장에는 재사용하지 않는다.
- `ai_prompt_versions`: 초안→검토→승인→활성→폐기 lifecycle과 template hash를 가진다. 승인된 본문은 수정하지 않고 새 version을 만든다.
- `ai_queries`: 고객/현장 scope, prompt/approval JSON snapshot을 질의 시점에 저장한다. 이후 운영 객체 변경은 과거 snapshot을 바꾸지 않는다.
- `ai_operational_policies`: 전역 `*/*` 또는 정확한 고객/현장 scope별 kill switch, 요청·동시성·timeout·비용, 보존과 감사 내보내기 정책이다. 비밀 컬럼은 없다.
- `ai_operation_audit_events`: 승인·프롬프트·정책 변경과 호출 전 차단 사유의 원문 없는 감사 이벤트다.
- `ai_retention_audits`: 만료 질의별 payload 비식별화와 응답 삭제 동작, 보존된 hash를 기록한다.
- `ai_query_legal_holds`: 현재 고객·현장 질의에 대한 `ACTIVE`/`RELEASED` 보존 명령과 권한 근거, 설정·해제 actor/시각을 기록한다.

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

## 서버 운영 scope

파일럿 데이터 모델은 서버 인스턴스 자체를 단일 `customer_scope`·`site_scope` 경계로 본다. 계정, 문서, 채널, 보고서와 일반 검색 후보는 같은 서버 경계에 속하므로 개별 테이블에 중복 scope 열을 두지 않는다. 외부 AI 테이블의 기존 `customer_scope`, `site_scope`는 전송 승인과 감사 snapshot을 위한 값이며 서버 경계와 다른 값을 일반 업무 멀티테넌시로 해석하지 않는다.

API에 다른 scope가 들어오면 행 조회 전에 fail-closed로 거부한다. 따라서 다른 scope의 문서 ID와 존재하지 않는 ID는 외부 응답에서 구분되지 않는다. scope 거부는 `activity_history`의 `scope.access_denied`로 남기며 요청 사용자, 요청 scope와 서버 scope를 감사 안에서만 비교한다.

이번 전환은 업무 테이블 schema와 행을 바꾸지 않는다. 기존 단일 현장 DB를 새 코드로 열고 다시 이전 코드로 여는 동안 `documents`, `document_versions`, `field_comments`, `reports`, `report_sources`, 채널·계정 테이블의 행 수와 주요 ID/hash가 그대로여야 한다. 여러 scope 지원은 이 모델의 호환 변경이 아니라 별도 migration이 필요한 후속 설계다.

### 역할별 권한 정책

FastAPI 서버의 `app/core/auth.py`와 WPF `RolePermissionPolicy`는 다음 기준을 공유한다.

| 권한 영역 | FastAPI 기준 | WPF 기준 |
| --- | --- | --- |
| 문서 등록/버전 등록/태그 변경/작업순서 변경 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead` | 문서 등록, 파일 업로드, Drag & Drop, 상태 변경, 공개, 작업판 버튼 활성 |
| FieldComment 등록 | 문서 쓰기 role + `team-member`, `viewer` | 문서 뷰어의 현장 코멘트 작성은 기본 role 전체 허용 |
| FieldComment 위험 원천 최종 결정 | `FIELD_COMMENT_DECIDE_ROLES`. `red` 또는 상충 원천은 `analyzed_by`와 결정 actor가 달라야 함 | 서버 거부 문구를 정제해 표시하고 같은 분석자의 결정 완료로 표시하지 않음 |
| 접근 로그 조회 | `admin`, `system-admin` | WPF는 로컬 열람/다운로드 차단 로그를 기록하고 서버 조회 UI는 아직 두지 않는다 |
| 보고서 작성 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | 보고서 버튼 활성 |
| 보고서 목록·상세·원천 조회 | 기본 role 전체. 모든 고정 원천의 현재 상태와 연결 채널 멤버십을 재검사 | 비노출 보고서를 로컬 목록에 합치지 않고 원천 없음·비공개 안내 사용 |
| AI ground-truth 사례 등록·2차 승인, dataset 작성·구성·검토 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` | `AI 정답셋`과 `사례·원천 구성` 화면 사용 |
| AI ground-truth dataset 1·2차 승인·폐기 | `admin`, `system-admin`, `document-admin`, `department-manager` | 독립 사용자 조건을 만족하는 상태에서만 승인/폐기 버튼 활성 |
| 채널 관리/인수인계 확인 현황 | 채널 생성은 문서/작업순서 쓰기 role, 조회와 수신확인은 채널 멤버십 또는 `admin`, `system-admin` 기준 | 채널 관리와 인수인계 확인 현황 버튼은 문서 등록 권한과 같은 role에서 활성 |
| 파일 감시 | 서버 전용 권한 그룹은 아직 없음 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| controlled copy 다운로드 | 현재 공개 버전, 1회성 티켓, 사용자·세션 일치, 경로·크기·SHA-256 재검증 | `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager` |
| 사용자 관리 | 계정 생성·role/상태 변경·비밀번호 재설정·세션 조회/폐기 | `admin`, `system-admin` |

### 로컬 계정과 서버 계정 운영 기준

WPF 사용자 관리는 위 role 중 하나만 선택할 수 있다. 새 사용자 ID는 `user-{loginId}` 형식으로 자동 생성된다.

`user_accounts.must_change_password`는 임시 비밀번호 로그인 후 정상 API 사용을 막는 서버 기준 값이고 `password_changed_at`은 본인 비밀번호 변경 완료 시각이다. 계정 생성과 관리자 비밀번호 재설정은 `must_change_password = true`, 본인 변경 성공은 `false`로 바꾸며 모든 기존 세션을 폐기한다. `auth_sessions`에는 원문 refresh token이 아니라 hash만 저장하고, 계정 잠금·비활성화·role 변경·비밀번호 변경/재설정·관리자 폐기 시 즉시 `REVOKED`로 전환한다.

WPF 표준 로그인과 사용자 관리는 운영 HTTPS 서버 세션과 서버 계정 운영 화면을 사용한다. 로컬 SQLite 계정 row와 화면은 기존 데이터·단위 테스트 호환을 위해 보존하며 서버 계정과 자동 병합하거나 같은 ID의 row를 서로 덮어쓰지 않는다.

설정한 승인 `FLOWNOTE_API_BASE_URL`에서 서버 로그인이 성공하면 WPF 현재 세션의 사용자 ID, 로그인 ID, 표시 이름, role은 서버 응답을 우선한다. 같은 로그인 ID의 로컬 계정 정보가 다르더라도 서버 사용자 정보를 화면 표시, 버튼 권한, 서버 동기화 작성자 ID에 사용하고 로컬 계정 row는 자동 덮어쓰지 않는다.

설정한 승인 HTTPS 주소의 401·403뿐 아니라 인증서·주소·방화벽·시간 초과 오류에서도 HTTP나 로컬 계정 fallback으로 우회하지 않는다. 현재 표준 실행에는 서버 URL 미설정 로컬 로그인 경로가 없다.
## 서버 복구 경계와 재결합 이력

- 서버 `server_identity`는 단일 행이며 불변 `server_instance_id`, 단조 증가시키는 `server_epoch`, schema/API contract 범위를 가진다. DB 백업에는 instance ID가 포함되며 복구 직후 epoch 증가 절차로 복구 경계를 만든다.
- 서버 `reconciliation_runs`와 `reconciliation_items`는 run, 원래 client item, 양쪽 hash, 이전·현재 server ID, 판정, 승인자·사유·종결 상태를 보존한다. 상태는 run `REVIEW_REQUIRED/APPLIED/FAILED`, item 판정 `CONFIRMED/ABSENT/DIVERGED`, 조치 `REBOUND/REQUEUE/CONFLICT`, 승인 종결 `REBOUND_CONFIRMED/REQUEUED_FOR_RETRY/APPROVED_CONFLICT`다. 실패 run과 divergence row는 삭제하지 않는다.
- WPF `server_bindings`는 정규화 URL별 승인된 instance/epoch와 관측값, 복구 pilot run·backup set·승인·담당자·장애 코드, 수렴 상태를 함께 둔다. `RECONCILIATION_REQUIRED`와 `POST_APPROVAL_RESTART_REQUIRED`에서는 자동 전송과 polling을 금지한다. 정상 manifest를 다시 읽으면 장애 코드를 비우고 `POST_APPROVAL_VERIFICATION_REQUIRED`로 바꾸지만, 이 상태만으로 안전 수렴을 확정하지 않는다.
- WPF `reconciliation_runs/items`는 서버 판정 원문과 로컬 적용 결과를 보존한다. 기존 `server_id_mappings`, `server_sync_queue`, `server_notification_cursors`, `server_notification_messages` 행은 삭제하지 않고 갱신 또는 종결 상태로 전환한다.

## WPF 문서 충돌 snapshot과 해결 이력

- `server_sync_queue.base_snapshot_hash_sha256`는 enqueue 시점의 서버 revision, 최신/공개 version ID, 상태와 서버 태그 snapshot을 canonical JSON으로 묶은 SHA-256이다.
- `server_read_back_json`, `server_conflict_hash_sha256`는 409 직후 다시 읽은 서버 문서 권위와 선택 파일 hash를 보존한다. `allowed_actions_json`, `retry_not_before`는 해당 충돌에 허용된 행동과 read-back 불일치 보호 기간을 고정한다.
- `source_preserved_path`는 새 버전 전송에 사용할 로컬 원본의 보존 위치다. 원본을 복사하거나 덮어쓰지 않으며, 전송 직전 hash가 `local_file_hash_sha256`와 다르면 새 mutation을 만들지 않는다.
- 해결 시 `resolution_action`, `resolution_reason`, `resolved_by`, `resolved_at`을 원 큐에 남긴다. 해결 사유는 10자 이상이며 문서 관리 역할의 사용자가 수행한다. `KEEP_SERVER`는 원 큐를 `DISCARDED`로 종결하고, `REGISTER_NEW_VERSION`은 원 큐를 보존 종결한 뒤 새 `sync_id`·idempotency key의 `PENDING` mutation을 추가한다.

## 문서 검토·공개 승인 모델

- `document_approvals`는 한 검토 요청의 현재 projection이다. `document_id`, 정확한 `version_id`, 요청 mutation이 선점한 `base_document_revision`, `source_file_hash_sha256`, 요청자, 검토자 사용자 ID 또는 role, 요청 사유와 기한을 고정한다.
- 상태는 `REQUESTED`, `APPROVED`, `REJECTED`, `CANCELLED`, `STALE`, `PUBLISHED`다. 반려·취소·stale 요청을 다시 대기 상태로 되돌리지 않으며, 수정본은 새 mutation key로 새 요청을 만든다.
- `document_approval_events`는 `REQUESTED`, `APPROVED`, `REJECTED`, `CANCELLED`, `MARKED_STALE`, `PUBLISHED`, `PUBLICATION_WITHDRAWN` append-only 이력이다. actor·role·문서 revision·version·hash·사유를 당시 값으로 보존한다.
- `document_approval_mutation_receipts`와 공통 `sync_mutation_receipts`, `audit_event_envelopes`, `activity_history`는 요청·결정·취소와 같은 transaction에 포함된다. 같은 key와 intent는 기존 응답을 재생하고 다른 intent는 `409 IDEMPOTENCY_KEY_REUSED`다.
- `documents.publication_approval_id`는 새 공개본의 승인 근거를 가리키며 `publication_origin = APPROVAL_WORKFLOW`를 사용한다. migration 전 공개본은 승인 근거를 추정하지 않고 `publication_origin = LEGACY_PUBLICATION`, null 승인 ID로 유지한다.
- 승인 공개를 취소하면 아직 `ISSUED`인 Android 열람 grant와 controlled copy grant는 `FAILED`로 바뀐다. 이미 소비된 복사본은 회수됐다고 추정하지 않고 기존 소비·감사 이력을 유지한다.

## 운영 준비도 읽기 모델

`operational-readiness-v1`은 DB entity나 권위 snapshot이 아니다. 공통 `audit_event_envelopes` snapshot anchor와 현재 권위 테이블을 요청 시점에 결합하는 재생성 가능 projection이다. 따라서 대시보드 조회·페이지 이동·상세 조회는 문서, FieldComment, 보고서, 작업순서, 채널/인수인계, 단말, 세션, 재결합 item, 공통 receipt와 감사 row를 생성·수정·삭제하지 않는다.

준비도 상태는 `NORMAL`, `WARNING`, `BLOCKED`, `NO_DATA`다. 영역별 수치는 권한으로 평가한 대상 중 정상 대상 수와 주의/차단 조치 row 수이며, 한 대상에 여러 blocker code가 있어도 가장 높은 상태의 조치 row 한 건으로 묶는다. `NO_DATA`는 원천이 0건이라는 뜻이 아니라 집계 실패 또는 해당 영역 권한 부족으로 수치를 제공하지 않았다는 뜻이다. 활성 채널 제한 대상은 비회원의 평가 대상과 모든 합계에서 제외한다.

조치 row의 안정 식별자는 영역·대상 유형·대상 ID의 결정적 hash다. `blockerCodes[]`, 현재 상태와 source revision, 담당 역할·담당자, 다음 행동, 기존 업무 화면 route, 가장 오래된 근거 시각, 선택적 최신 공통 event ID를 가진다. 해결 여부를 저장하는 열은 두지 않으며 현재 권위 상태에서 blocker가 다시 계산되지 않을 때 해결된 것으로 판정한다. AI 실제 현장 준비도는 `ANONYMOUS_FIELD` 계열 projection으로 별도 구획하고 `SYNTHETIC`, `TEST` 계열을 합산하지 않는다.

## Android 작업순서 원천 필드

`field_comments`에는 선택적인 `source_type`, `source_id`, `source_revision`, `server_scope`, `intent_hash_sha256`를 둔다. Android 작업순서에서 시작한 기록은 `source_type = WORK_SEQUENCE_ITEM`이며 `source_id`는 `work_sequence_items.item_id`, `source_revision`은 선택 당시 `work_sequence_boards.board_revision`이다. `document_id`와 `document_version_id`는 그 시점의 현재 공개 문서를 함께 고정한다. 이 필드들은 기존 FieldComment 원천 불변 필드와 같이 update할 수 없다.

`handovers`에도 `source_revision`, `server_scope`, `intent_hash_sha256`를 추가한다. 작업순서 원천은 기존 `source_type`, `source_id`와 함께 저장하고 당시 공개 문서는 `related_document_id`, `related_document_version_id`에 둔다. 공개 문서가 없는 작업 항목의 인수인계는 두 related 필드를 `NULL`로 저장할 수 있다.

Android 작업순서 snapshot은 서버 DB 엔티티가 아니다. 단말 SharedPreferences에 Keystore AES-GCM 암호문으로 저장하며 cache key는 정규화 서버 URL, customer scope, site scope, user ID, device ID의 SHA-256이다. 목록·상세 snapshot은 7일 보존하고 outbox SQLite transaction과 결합하지 않는다. 서버의 `ActivityHistory`에는 `work_sequence.android_read`와 `field_comment.work_sequence_source_linked`를 기록해 사용자·단말·board revision·item ID를 대조할 수 있게 한다.
