# 보존 동기화 실패 무손실 전환

## 목적

`server_sync_queue.status = FAILED`인 누적 행을 정상 신규 흐름과 분리해 진단하고, 운영자가 승인한 행만 현재 action의 별도 큐로 전환한다. 기존 큐 행, 구 원천 행, 첨부와 로컬 파일은 수정하거나 삭제하지 않는다.

이 계약은 2026-07-16 현재 `LegacySyncMigrationService`와 `FlowNote.Windows.SyncMigrationTool` 구현 기준이다.

## 읽기 전용 분류

분류 우선순위는 아래 순서로 고정한다. 먼저 일치한 한 분류만 사용하므로 모든 FAILED 행은 중복 없이 정확히 하나의 분류에 속한다.

1. `구 FieldNote/첨부`: `field_note`, `field_note_attachment` 또는 구 action
2. `구 형식 create`: `action = create`
3. `로컬 파일 누락`: 현재 action이지만 오류 또는 실제 원천 파일이 없음
4. `선행 서버 ID 누락`: 문서, 버전, FieldComment 또는 보고서 근거 매핑이 선행 조건임
5. `실제 서버/인증 오류`: 서버 URL, 인증, 네트워크, HTTP 오류와 나머지 서버 오류

운영 상태는 다음 네 가지다.

| 상태 | 의미 | 승인 실행 |
| --- | --- | --- |
| `자동 전환 가능` | 원천과 파일이 있고 현재 action을 단일하게 결정할 수 있음 | row별 승인 가능 |
| `관리자 확인 필요` | 구 FieldNote 의미 전환 또는 구 열람 로그 이벤트 해석이 필요함 | 내용을 확인한 row만 승인 가능 |
| `원본 누락으로 전환 불가` | 원천 행이나 필수 파일이 없음 | 차단. 한글 복구 조치를 출력 |
| `계속 보존` | 현재 action이며 선행 ID 또는 서버/인증 조치 후 기존 큐를 재시도해야 함 | 신규 큐를 만들지 않음 |

## 실행 방법

기본 실행은 dry-run이다. SQLite를 `ReadOnly` 모드로 열며 스키마 초기화, 감사 행 생성, 큐 변경을 하지 않는다. 결과 JSON에는 실제 FAILED 수, 분류 합계, 상태 합계, 안정된 `planHash`, 모든 원천 row, 원천 존재 여부, 파일 존재 여부, 대상 action과 예상 idempotency key가 들어간다.

```sh
dotnet run --project apps/windows/src/FlowNote.Windows.SyncMigrationTool -- \
  --database data/local/flownote.local.sqlite
```

승인 실행은 직전 dry-run의 row ID와 `planHash`를 함께 요구한다. 해시가 달라졌으면 실행을 거부하고 새 dry-run을 요구한다.

```sh
dotnet run --project apps/windows/src/FlowNote.Windows.SyncMigrationTool -- \
  --execute \
  --database data/local/flownote.local.sqlite \
  --approve 79,80 \
  --approved-by "운영 관리자" \
  --plan-hash "DRY_RUN_PLAN_HASH"
```

구 FieldNote 첨부는 연결된 구 FieldNote 본문을 같은 실행에서 함께 승인하거나 본문을 먼저 승인해야 한다. 승인자는 원천 본문, 작성자, 작성 시각, 첨부, 원천 ID를 확인해야 한다.

## 무손실 및 멱등성 계약

- 기존 `server_sync_queue` 행의 상태, 오류, 시도 횟수와 ID를 수정하지 않는다.
- 새 큐는 현재 action, 결정적 target ID, 현재 형식 idempotency key, `PENDING`, `attempt_count = 0`으로 별도 생성한다.
- `server_sync_migration_audit.source_queue_id`와 `target_idempotency_key`는 각각 유일하다.
- 두 번째 승인 실행은 감사 행을 확인하고 원천, 큐, 감사를 모두 0건 생성한다.
- 구 FieldNote는 결정적 새 FieldComment ID로 복제한다. 작성자, 보고자, 작업자, 본문, 정리/분석 내용, 상태, 생성 시각을 그대로 보존한다.
- 구 첨부는 결정적 새 첨부 ID와 새 FieldComment ID로 연결하고 파일 경로, 원본 파일명, hash, 작성자, 촬영/생성 시각을 그대로 보존한다.
- 감사 JSON은 전환 당시 구 원천의 전체 column snapshot과 `legacy_domain_name = FieldNote`를 남겨 구 명칭과 원천 ID를 추적한다.

## 검증 기준

실행 전후 아래 값을 비교한다.

```sql
SELECT status, COUNT(*) FROM server_sync_queue GROUP BY status;
SELECT COUNT(*) FROM server_sync_migration_audit;
SELECT idempotency_key, COUNT(*) FROM server_sync_queue GROUP BY idempotency_key HAVING COUNT(*) > 1;
SELECT entity_type, local_id, local_version_no, COUNT(*)
FROM server_id_mappings
GROUP BY entity_type, local_id, local_version_no
HAVING COUNT(*) > 1;
PRAGMA quick_check;
PRAGMA foreign_key_check;
```

dry-run 전후에는 DB 파일 SHA-256과 상태별 큐 합계가 같아야 한다. 승인 후에는 FAILED/SYNCED와 원천 행 수가 같고 PENDING, 감사, 전환 원천만 승인 수만큼 증가해야 한다. 서버 중단·401은 실제 서버 호출 실패이므로 시도 횟수가 증가할 수 있지만, 선행 ID 누락·파일 누락·구 action 보류와 이 전환 도구 자체는 서버 호출을 하지 않으므로 `attempt_count`를 증가시키지 않는다.
