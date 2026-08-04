# 0003 Document Approval Workflow

기존 문서와 공개 이력을 보존하면서 정확한 version·revision·file hash에 묶인 검토·공개 승인 근거를 추가하는 additive schema다. 실제 생성 기준은 `app/db/models_document_approval.py`와 `app/db/models_core.py`이며, 앱 시작 시 ORM metadata가 누락 테이블을 만든 뒤 `schema_migrations`에 적용 버전을 기록한다.

## Version

- `schema_migrations.version`: `0003_document_approval_workflow`
- 추가 테이블: `document_approvals`, `document_approval_events`, `document_approval_mutation_receipts`
- 추가 열: `documents.publication_approval_id`, `documents.publication_origin`
- 기존 테이블·row 삭제·rename: 없음

## 보존과 기본값

- migration 전 공개본은 승인 ID를 추정하지 않고 `publication_origin = LEGACY_PUBLICATION`, `publication_approval_id = null`로 유지한다.
- migration 뒤 승인 흐름으로 공개한 문서만 `publication_origin = APPROVAL_WORKFLOW`와 승인 ID를 저장한다.
- `document_approval_events`는 append-only이며 상태 변경이나 삭제로 과거 요청·결정 근거를 덮어쓰지 않는다.
- 승인 취소가 현재 공개본과 연결된 경우 공개 포인터와 아직 사용하지 않은 열람 grant만 무효화한다. 문서 version, 소비된 controlled copy와 기존 열람·감사 이력은 삭제하지 않는다.

## 검증

업그레이드 전후 기존 문서·버전·공개 포인터·파일 hash와 감사·mutation receipt의 row 수 및 고유 key 집합을 대조한다. 이전 공개본은 모두 `LEGACY_PUBLICATION`이고 승인 ID가 비어 있어야 하며, 새 승인 테이블과 `publication_approval_id` 인덱스가 생성되어야 한다. 테스트 SQLite, 업로드 파일과 로그는 삭제하거나 초기화하지 않는다.
