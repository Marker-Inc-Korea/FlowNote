# 0002 Common Mutation Receipts

기존 도메인 감사와 mutation receipt를 유지하면서 공통 조회·재시도 기준을 추가하는 additive schema다. 실제 생성 기준은 `app/db/models_common_audit.py`이며 앱 시작 시 ORM metadata가 누락 테이블을 만든 뒤 `schema_migrations`에 적용 버전을 기록한다.

## Version

- `schema_migrations.version`: `0002_common_mutation_receipts`
- 추가 테이블: `audit_event_envelopes`, `sync_mutation_receipts`
- 기존 테이블 변경·삭제·rename·row backfill: 없음

## 불변식

- `sync_mutation_receipts.operation_key`는 서버 전체에서 UNIQUE다.
- 같은 operation key와 같은 event/target/intent는 최초 성공 또는 거부·충돌 결과로 수렴한다.
- 같은 key의 다른 intent는 `409 IDEMPOTENCY_KEY_REUSED`로 거부하며 기존 receipt를 변경하지 않는다.
- 성공 업무 변경, 기존 도메인 receipt, 공통 event/receipt는 한 transaction에서 commit한다.
- 기존 `activity_history`와 도메인 receipt는 그대로 조회되며 공통 필드가 없는 값을 추정하지 않는다.
- 공통 payload는 정제 code, ID, revision, hash와 연결 ID만 저장한다. token, 비밀번호, 고객 원문, 로컬 절대경로와 불필요한 개인정보는 금지한다.

## 보존 검증

업그레이드 전후 다음 항목의 row 수와 기존 PK/고유 key 집합이 같아야 한다.

- `activity_history`
- `document_mutation_receipts`
- `field_comment_review_mutation_receipts`
- `report_mutation_receipts`
- `work_sequence_mutation_receipts`
- `reconciliation_runs`, `reconciliation_items`
- 문서·FieldComment·보고서·작업순서 원천 테이블

WPF `server_sync_queue`는 별도 로컬 SQLite 소유이므로 이 서버 migration의 대상이 아니다. 서버 DB와 WPF DB 경로를 혼용하지 않으며 migration 검증 과정에서도 WPF 큐·테스트 SQLite·테스트 파일·로그를 삭제하거나 초기화하지 않는다.
