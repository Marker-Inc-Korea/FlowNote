# 2026-06-24 API SQLite MVP 기록

이 문서는 FastAPI 서버의 SQLite MVP 작업 기록을 현재 코드 기준으로 정리한 것이다.

## 현재 서버 기준

- FastAPI 앱은 `/api/v1` 아래에 인증·서버 계정, 승인 단말, 문서와 controlled copy, FieldComment, 태그, 접근 로그, 작업순서, 채널/인수인계, 보고서, AI 검색 근거 후보·회귀 평가와 외부 AI 질의 안전장치, sync manifest·reconciliation 라우터를 제공한다.
- 기본 DB URL은 `sqlite:///./data/flownote.sqlite3`이다.
- 테스트 DB 기본값은 `sqlite:///./data/flownote.test.sqlite3`이다.
- 파일 저장소 기본값은 `./storage`이다.
- 개발 기본 관리자 계정은 DB가 비어 있을 때 시드된다.

## 스키마 범위

- 사용자와 세션: `user_accounts`, `roles`, `user_roles`, `auth_sessions`, `operator_profiles`
- 서버 식별과 복구: `server_identity`, `reconciliation_runs`, `reconciliation_items`
- 문서와 버전: `documents`, `document_versions`
- 파일 객체: `file_objects`
- 태그: `tag_definitions`, `document_tags`
- 승인 단말: `terminal_devices`
- 현장 코멘트: `field_comments`, `field_comment_attachments`, `field_comment_review_mutation_receipts`
- 현장 입력과 작업내역 기반: `comment_templates`, `work_records`, `work_record_versions`
- 열람 이력: `document_access_logs`
- 작업순서: `work_sequence_boards`, `work_sequence_items`, `work_sequence_change_history`, `work_sequence_mutation_receipts`, `work_sequence_notification_candidates`
- 채널/인수인계: `notification_channels`, `notification_channel_members`, `channel_messages`, `handovers`, `handover_receipts`
- 보고서: `reports`, `report_sources`, `report_mutation_receipts`
- AI 검색 후보·평가: `ai_search_candidates`, `ai_search_ground_truth_cases`, `ai_search_ground_truth_provenance`, `ai_ground_truth_dataset_versions`, `ai_ground_truth_dataset_cases`, `ai_search_evaluation_runs`, `ai_search_evaluation_cases`, `ai_evaluation_dataset_bindings`
- 외부 AI 안전장치·운영·감사: `ai_prompt_versions`, `ai_queries`, `ai_query_evidence_candidates`, `ai_query_citations`, `ai_query_legal_holds`, `ai_call_attempts`, `ai_transfer_approvals`, `ai_sensitive_data_policies`, `ai_operational_policies`, `ai_provider_onboarding_reviews`, `ai_operation_audit_events`, `ai_retention_audits`
- 제한 다운로드: `controlled_copy_grants`
- Android 앱 내부 열람: `android_document_view_grants`
- 마이그레이션 기록: `schema_migrations`
- 공통 감사: `activity_history`

## 구현된 주요 흐름

- 로그인 후 Access Token과 Refresh Token을 발급한다.
- Refresh Token 사용 시 토큰을 회전하고 이전 토큰 재사용을 거부한다.
- 문서 등록 시 파일을 서버 로컬 저장소에 저장하고 SHA-256, 크기, MIME/확장자를 기록한다.
- 새 문서 버전 등록 시 이전 최신 버전은 `SUPERSEDED`로 바뀐다.
- 공개 문서는 명시적으로 공개 버전을 지정해야 조회할 수 있다.
- 작업순서 변경은 `board_revision`, FieldComment 검토는 `review_revision`, 보고서 저장은 `report_revision`과 내용/source 집합 hash를 서버 권위값으로 사용하고, 각 도메인 mutation receipt가 동일 key 재시도의 최초 결과를 보존한다.
- sync manifest는 서버 instance/epoch와 계약 범위·알림 high-water cursor를 제공하고, reconciliation은 WPF 큐 inventory를 판정한 뒤 관리자 승인으로만 적용한다.
- controlled copy는 현재 공개 버전에만 발급되며 사용자·세션에 묶인 짧은 만료의 1회성 티켓과 SHA-256 검증을 사용한다.
- AI 검색 근거 후보는 공개 문서 버전, FieldComment, 작업순서 이력, 보고서 source에서 재생성한다.
- ground-truth 사례는 서로 다른 두 사용자의 승인을 거쳐 활성화하고, 승인 사례 집합은 불변 dataset version으로 묶어 평가 run에 고정한다.
- FieldComment 원천 핵심 필드는 생성 뒤 불변이며 검토 변경은 담당자·기한·전이 사유와 원천 hash를 포함한 감사 snapshot으로 분리한다.
- 외부 AI provider 직전 경계는 활성 고객·현장 민감정보 정책, 원천 권한, 최소 발췌·최대 원천 수와 인용 ID를 검사한다. generic 네트워크 adapter는 명시적 test scope에만 있고 provider별 운영 client는 없다.
- 서버 lifespan 스케줄러와 `system-admin` 일괄·단일 즉시 실행 API는 만료된 질의 payload를 비식별화하고 저장 응답 원문을 삭제하면서 hash와 감사 메타데이터를 보존한다. 활성 legal hold가 있는 질의는 해제 전까지 세 만료 경로에서 제외된다.
