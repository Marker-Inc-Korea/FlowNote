# 서버 동기화 실패와 재시도 UX

이 문서는 2026-07-21 현재 `ServerSyncService`, 실패 진단 코드와 WPF 이력 화면 기준이다. 아래 누적 건수는 당시 보존 DB의 검증 기록이며 고정 기대값이 아니다.

## 화면 기준

서버 동기화 상태는 기존 `이력` 창을 확장해 확인한다. 창 안에는 `활동 이력`, `동기화 큐`, `서버 재결합` 탭을 둔다.

`동기화 큐` 탭은 다음 컬럼을 표시한다.

화면 상단 요약의 대기, 실패, 보류, 완료 수는 목록 표시 한도와 관계없이 SQLite 전체 큐를 집계한다. 목록에는 현재 최대 500건을 표시하며, 요약에 전체 건수와 실제 표시 건수를 함께 보여준다.

- `상태`: `대기`, `실패`, `충돌`, `완료`, `폐기`
- `우선순위`: 운영자가 먼저 확인할 순서. `10 설정 필요`, `11 로그인 필요`, `12 연결 확인`, `20 파일 확인`, `30 문서 먼저`, `31 버전 먼저`, `32 FieldComment 먼저`, `33 근거 먼저`, `50 재시도`, `80 별도 정리`, `81 별도 전환`, `90 완료`
- `분류`: 서버 URL 미설정, 인증 만료, 네트워크 실패, 로컬 파일 누락, 선행 문서 미동기화, 선행 문서 버전 미동기화, 선행 FieldComment 미동기화, 보고서 근거 미동기화, 구 FieldNote 큐, 구 형식 큐, 실제 서버 오류, 재시도 가능, 완료
- `대상`: 문서, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 접근 로그, 보고서
- `작업`: 문서 전송, 버전 전송, 공개 전송, 상태 전송, FieldComment 전송, 검토 변경 전송, 첨부 전송, 열람 시작/종료/자동 종료/다운로드 차단 전송, 보고서 서버 저장
- `시도`: 서버 전송 시도 횟수
- `마지막 시도`: 마지막 재시도 시간
- `조치`: 운영자가 먼저 할 일
- `실패 사유`: 사용자가 조치할 수 있는 한글 실패 문구
- `충돌 코드`: stale revision, 기준 버전, 공개본 경쟁, 삭제 재전송, 멱등키, SHA-256 불일치를 구분하는 서버 코드

`재시도` 버튼은 현재 `PENDING`, `FAILED` 큐를 다시 전송한다. 서버 URL 또는 로그인 토큰이 없으면 재시도하지 않고 “서버 URL 또는 로그인 정보가 없어 재시도할 수 없습니다. 서버 설정과 로그인을 확인하세요. 로컬 데이터는 삭제되지 않습니다.”를 표시한다.

`CONFLICT`는 일반 재시도 대상이 아니다. 운영자는 충돌 행을 선택하고 사유를 입력한 뒤 다음 중 하나를 고른다.

- `로컬 변경 재시도`: 서버 상세를 다시 읽어 최신 `revision`, 최신/공개 버전 ID를 로컬과 큐에 저장하고 `PENDING`으로 바꾼 뒤 로컬 변경을 새 서버 기준에서 재시도한다. 파일/공개/상태 의미가 여전히 맞는지 관리자가 확인한 경우에만 사용한다.
- `서버본 유지·폐기`: 로컬 전송 요청을 `DISCARDED`로 종결한다. 로컬 문서와 파일, 충돌 원 응답, 큐 행은 삭제하지 않는다.

두 선택은 `resolution_action`, 사유, 해결자, 해결 시각과 `activity_history`에 남고 앱 재시작 뒤에도 표시된다. 사유 없이 버튼을 누를 수 없다.

`서버 재결합` 탭은 서버 URL·instance·epoch 변경 또는 cursor 역행으로 자동 전송과 polling이 중지된 경우에 사용한다. `판정 실행`은 로컬 `server_sync_queue` 전체를 idempotency key와 선택적 파일 hash, 기존 mapping과 함께 서버에 보내 `CONFIRMED/REBOUND`, `ABSENT/REQUEUE`, `DIVERGED/CONFLICT` 판정을 저장한다. `승인 적용`은 관리자 사유가 필수이며 모든 항목의 서버 제안 조치를 그대로 확인한다. 적용되면 재결합은 mapping과 큐 상태를 한 transaction에서 갱신하고, binding을 새 instance/epoch로 활성화하며, 해당 scope의 cursor를 0부터 재추적한 뒤 `PENDING` 전송을 재개한다. 처리한 `message_id`, 기존 큐와 로컬 원천은 삭제하지 않는다.

재시도 루프는 선행 문서, 문서 버전, FieldComment, 보고서 근거가 아직 서버 ID로 연결되지 않은 항목을 `보류`로 집계한다. 보류 항목은 `FAILED` 상태와 한글 실패 사유를 유지하지만 실제 서버 호출을 하지 않고 `attempt_count`를 올리지 않는다. 같은 재시도 배치 안에 선행 항목이 같이 있으면 문서 등록이 먼저 처리된 뒤 후행 버전, 공개, 상태, FieldComment, 검토 변경, 첨부, 접근 로그, 보고서 항목을 이어서 전송한다.

## 실패 문구

- 서버 URL 미설정: `서버 URL이 설정되지 않아 전송하지 못했습니다. 서버 설정 후 재시도하세요.`
- 네트워크 실패: `서버에 연결하지 못했습니다. 네트워크와 서버 실행 상태를 확인하세요.`
- 서버 응답 시간 초과: `서버 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.`
- 인증 만료: `로그인이 만료되었거나 서버 인증이 해제되었습니다. 다시 로그인하세요. 로컬 데이터는 삭제되지 않습니다.`
- 선행 문서 미동기화: `선행 문서가 아직 서버에 전송되지 않았습니다. 문서 동기화 후 다시 시도하세요.`
- 선행 문서 버전 미동기화: `선행 문서 버전이 아직 서버에 전송되지 않았습니다. 문서 버전 동기화 후 다시 시도하세요.`
- 선행 FieldComment 미동기화: `선행 FieldComment가 아직 서버에 전송되지 않았습니다. FieldComment 동기화 후 다시 시도하세요.`
- 구 FieldNote 큐: `구 FieldNote 큐는 현재 FieldComment 동기화 대상이 아니어서 자동 전송하지 않았습니다. 관리자 검토 후 FieldComment 전환 또는 별도 마이그레이션으로 정리하세요. 로컬 데이터는 삭제되지 않습니다.`
- 구 형식 create 큐: `구 형식 create 큐는 현재 서버 동기화 계약의 자동 전송 대상이 아닙니다. 원본 이력은 보존하고 관리자 검토 후 현재 action으로 별도 마이그레이션하세요. 서버 호출과 시도 횟수 증가는 수행하지 않았으며 로컬 데이터는 삭제되지 않습니다.`

## 문서 버전/공개/상태 우선순위

서버-WPF 동기화는 로컬 저장을 먼저 성공시키고, 재시도 시 같은 문서 또는 보고서 근거 단위의 선행 조건을 우선한다. 현재 재시도 순서는 문서 등록, 문서 버전, 공개, 상태, FieldComment, FieldComment 검토, 첨부, 접근 로그 시작/종료/자동 종료/다운로드 차단, 보고서 저장이다. 문서 최초 등록이 서버에 성공해야 문서 버전, FieldComment, 첨부, 접근 로그가 서버 문서 ID에 연결된다.

신규 큐는 서버에서 마지막으로 확인한 `revision`, 최신 버전 ID, 공개 버전 ID와 로컬 파일 SHA-256을 snapshot으로 남긴다. 구 큐처럼 base revision이 없는 호환 경로에서 서버에 같은 번호의 버전이 이미 있으면 SHA-256이 같은 경우에만 로컬 `server_version_id`, `synced_at`, `server_id_mappings`를 복구한다. hash가 다르면 `FILE_HASH_MISMATCH` 충돌이다. 신규 큐는 서버가 revision 확인 뒤 다음 버전 번호를 배정하므로 로컬 번호와 서버 번호의 우연한 일치를 성공 조건으로 쓰지 않는다.

공개는 항상 특정 로컬 버전 번호의 서버 버전 ID가 확인된 뒤 서버 publish API를 호출한다. 문서 상태는 현재 로컬 `documents.status`를 서버 상태 API에 반영한다. 상태가 `PUBLISHED`이면 공개 대상 버전의 서버 버전 ID가 먼저 있어야 한다.

FieldComment 검토 큐는 enqueue 시점의 `review_revision`을 `base_domain_revision`에 고정하고 큐의 안정된 idempotency key를 서버 `mutationKey`로 보낸다. 서버가 409 `FIELD_COMMENT_STALE_REVIEW_REVISION` 또는 `IDEMPOTENCY_KEY_REUSED`를 반환하면 자동 재시도하지 않고 원 응답과 충돌 코드를 보존한다. 성공할 때는 응답 `review_revision`을 로컬 FieldComment에 반영한 뒤 큐를 종결한다.

FieldComment 첨부는 경로의 서버 comment ID를 multipart `parentCommentId`로, 로컬 파일의 SHA-256을 `fileSha256`으로 함께 보낸다. 부모 불일치, 요청/실파일 hash 불일치, 같은 key의 다른 파일 재사용은 충돌로 보존한다.

보고서 서버 저장은 로컬 보고서 문서와 `report_sources`를 먼저 남긴 뒤 `/api/v1/reports` 저장을 시도한다. enqueue 시 source 집합 hash를 고정하고 같은 안정 key를 `idempotencyKey`와 `mutationKey`로 보낸다. 성공 응답 source를 정규화해 응답 `source_set_hash_sha256`과 다시 대조한 뒤에만 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, report revision·내용/source 집합 hash와 `server_id_mappings`를 연결한다. 실패나 read-back 불일치는 기존 `server_sync_queue`의 `report/register_report` 항목과 원천 파일을 그대로 보존한다.

작업순서 보드/항목/이력은 WPF 로컬 큐의 양방향 동기화 대상이 아니다. 관리 화면은 서버 목록·상세 snapshot의 `board_revision`을 읽고 mutation key와 `baseBoardRevision`을 서버 API에 직접 보낸다. 409 `WORK_SEQUENCE_STALE_REVISION`이면 “다른 사용자가 먼저 변경”했다는 한글 안내와 최신 snapshot을 표시하며, 사용자가 확인한 뒤 다시 시도한다. 서버 미연결·503·시간 초과·호환 응답 실패에서는 로컬 row를 읽기 캐시/초안으로만 표시하고 확정 생성·순서·상태 변경을 비활성화한다. 실패 요청을 `server_sync_queue`에 넣지 않으며 기존 로컬 row와 테스트 기록은 삭제하지 않는다.

## 앱 시작 자동 재시도

앱 시작 시 서버 클라이언트가 구성되어 있으면 `RetryPendingAsync`를 한 번 실행한다. 실제 큐 처리 전에 sync manifest를 확인하며, contract 비호환·manifest 오류·복구 경계가 있으면 서버 mutation을 시작하지 않는다. 복구 경계는 기존 큐 상태를 바꾸지 않고 재결합 안내를 표시한다. manifest 조회 자체가 실패한 경우 현재 `PENDING` 큐는 원천을 유지한 채 `FAILED`와 확인 실패 사유로 바뀐다. 결과 요약은 메인 화면 하단 상태 표시줄에 표시하고 세부 시도, 실패, 성공은 `activity_history`와 `동기화 큐` 탭에서 확인한다.

로컬 저장 직후 문구는 `로컬 저장 완료 · 서버 확인 대기`, 큐 적재 뒤에는 `서버 확인 대기/재시도 필요`, 409 뒤에는 `충돌 · 관리자 선택 필요` 의미로 표시한다. 서버 응답 수신과 로컬 서버 ID/revision 매핑 저장까지 끝나 `SYNCED`가 된 경우에만 `서버 동기화 완료` 또는 `서버에 반영했습니다`를 표시한다. 다른 비완료 큐가 남아 있는 전체 재시도 요약도 완료로 표시하지 않는다.

알림함은 사용자 업무 알림을 우선하므로 자동 재시도 요약을 새 알림으로 만들지 않는다.

## 2026-07-10 실패 큐 분류와 잔여 PENDING 정리

정리 실행 전 WPF 공통 SQLite 기준은 `SYNCED` 520건, `FAILED` 293건, `PENDING` 300건이다. 기존 실패 293건은 아래 다섯 운영 분류로 나뉜다. 테스트 이력 보존 규칙에 따라 기존 큐와 SQLite 기록은 삭제하지 않는다.

현재 `sqlite3 data/local/flownote.local.sqlite`에서 `server_sync_queue`를 `entity_type`, `action`, `status`, `last_error`로 묶으면 실패 큐는 다음 패턴으로 나뉜다.

- 서버 URL 미설정 9건: 문서, 접근 로그 시작/종료/다운로드 차단, 문서 공개, 문서 상태, 문서 버전, FieldComment, FieldComment 첨부가 각 1건씩 남아 있다. 서버 URL과 로그인 상태를 다시 확인한 뒤 재시도한다.
- 선행 문서 미동기화 224건: 접근 로그 다운로드 차단 91건, 접근 로그 종료 26건, 접근 로그 시작 26건, FieldComment 21건, 문서 공개 20건, 문서 상태 20건, 문서 버전 20건. 같은 문서의 `document/register_document`가 먼저 서버 ID와 `synced_at`을 받아야 한다.
- 로컬 파일 누락 20건: `document/register_document`. 서버가 실행되어도 파일이 없으면 재시도할 수 없으므로 운영자가 원본 파일 위치를 복구해야 한다.
- 선행 FieldComment 미동기화 20건: `field_comment_attachment/register_field_comment_attachment`. 첨부보다 FieldComment 서버 등록이 먼저다.
- 구 FieldNote 큐 20건: `field_note/register_field_note` 10건, `field_note_attachment/register_field_note_attachment` 10건. 현재 명칭과 API는 FieldComment 기준이므로 자동 재전송 대상이 아니라 관리자 검토 후 전환 또는 별도 마이그레이션으로 정리한다.
- 실제 서버/설정 오류 9건: 현재는 모두 서버 URL 미설정이며 문서, 접근 로그 시작/종료/다운로드 차단, 문서 공개, 문서 상태, 문서 버전, FieldComment, FieldComment 첨부가 각 1건씩 남아 있다. 인증 만료, 네트워크 실패, 서버 응답 오류도 같은 운영 범주에서 원인을 조치한 뒤 재시도한다.

실행 전 `PENDING` 300건은 예전 로컬 큐 형식의 `create` action이다. `document/create` 60건, `document_version/create` 6건, `document_view_log/create` 72건, `field_comment/create` 144건, `field_comment_attachment/create` 18건이다. 2026-07-10 정리에서는 이 행을 삭제하거나 현재 action으로 임의 변환하지 않고 모두 `FAILED`와 구 형식 보류 사유로 분류했다. 정리 후 큐는 `SYNCED` 520건, `FAILED` 593건, `PENDING` 0건이며, 300건의 `attempt_count`는 모두 0으로 서버 호출이 없었음을 확인했다. 이후 재시도 코드도 `action = create`를 `MarkAttempt` 전에 보류하므로 서버 호출과 시도 횟수 증가 없이 같은 분류를 유지한다.

후속 FastAPI 연동 스모크까지 실행한 2026-07-10 기록은 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이다. 구 형식 create 300건은 모두 `attempt_count = 0`을 유지했고, `server_id_mappings` 767건의 중복 그룹은 0건이었다. 이 수치는 당시 공통 SQLite의 누적 기록이며 현재 코드의 고정 기대값이 아니다.

정리 도중의 중간 snapshot에는 `server_id_mappings` 648건이 기록되어 있었다. 이후 누적 실행으로 건수가 증가했으므로 648건을 현재 수치로 사용하지 않는다. 현재 코드 동작은 이미 서버에 존재하는 문서 버전을 `document_versions.version_no`로 찾아 `server_version_id`, `synced_at`, `server_id_mappings`를 복구하고 중복 업로드하지 않는 것이다. 큐 재등록도 `idempotency_key` 유니크 제약과 `ON CONFLICT(idempotency_key)`로 중복 행을 만들지 않는다.

controlled copy는 사용자가 즉시 수행하는 서버 발급·스트리밍 흐름이므로 이 큐의 대상이 아니다. 실패한 티켓을 재사용하거나 동기화 큐에 넣지 않고 새 요청에서 공개 상태와 권한을 다시 검사한다.

운영 우선순위는 다음 순서로 본다.

1. 서버 URL, 로그인, 네트워크 문제를 먼저 조치한다.
2. 로컬 파일 누락 문서는 파일 위치를 복구한다.
3. 같은 문서의 `document/register_document`를 먼저 동기화한다.
4. 같은 문서의 `document_version/register_document_version`과 `document_publish/publish_document_version`을 처리한다.
5. FieldComment를 먼저 동기화한 뒤 첨부, 검토 변경, 접근 로그를 재시도한다.
6. 구 FieldNote와 구 `create` 큐는 자동 재시도 대상에서 분리한다. 별도 전환 CLI의 읽기 전용 dry-run으로 원천·파일·대상 action을 확인하고, 운영자가 승인한 row만 신규 큐로 전환한다.

별도 전환은 기존 FAILED 큐의 상태·시도 횟수·오류를 바꾸는 재시도가 아니다. 승인 실행은 현재 action의 `PENDING` 큐와 감사 행을 추가하고 기존 큐와 파일을 계속 보존한다. 상세 분류, 명령과 검증 SQL은 [보존 동기화 실패 무손실 전환](./legacy-sync-migration.md)을 따른다.

## 검증 시나리오

1. 서버 URL이 없는 상태에서 문서를 등록한다.
2. 문서가 로컬 `documents`, `document_versions`에 남고 `server_sync_queue`에는 문서 전송 1건이 `FAILED`로 남는지 확인한다.
3. 같은 문서를 다시 큐에 넣어도 `idempotency_key` 기준으로 큐가 중복 생성되지 않는지 확인한다.
4. 같은 문서에 FieldComment와 첨부를 저장하고, 접근 로그 시작/종료를 남긴다.
5. 문서 v2 추가, publish, 상태 변경을 수행한다.
6. FieldComment, 검토 변경, 첨부, 접근 로그, 문서 버전, 공개, 상태, 보고서 큐가 로컬에 남고 실패 사유가 한글로 표시되는지 확인한다.
7. 서버를 켜고 같은 계정으로 로그인한 뒤 `재시도`를 누른다.
8. 문서, 문서 버전, 공개, 상태, FieldComment, 검토 변경, 첨부, 접근 로그, 보고서 큐가 `SYNCED`로 바뀌고 각 원천 테이블의 서버 ID와 `synced_at`, `server_id_mappings`가 채워지는지 확인한다.
9. 이미 `SYNCED`인 항목을 다시 큐에 넣어도 큐 건수와 시도 횟수가 증가하지 않는지 확인한다.
10. 만료된 토큰으로 재시도하면 인증 만료 문구가 표시되고, 로컬 데이터와 큐가 삭제되지 않는지 확인한다.
11. 사용자 A/B가 같은 base revision에서 각각 새 버전, 공개 교체, 상태 변경을 보내 하나만 성공하고 다른 요청이 `CONFLICT`로 남는지 확인한다.
12. 서버 삭제 뒤 오프라인 로컬 버전을 재전송하면 `DOCUMENT_DELETED`, 같은 멱등키의 다른 파일이면 `IDEMPOTENCY_KEY_REUSED`, 선언/저장 hash 불일치면 `FILE_HASH_MISMATCH`로 분리되는지 확인한다.
13. 충돌에서 로컬 재시도와 서버본 유지·폐기를 각각 선택한 뒤 앱을 재시작해 해결 사유·해결자·시각·감사가 보존되는지 확인한다.

WPF 스모크 테스트는 서버 미설정 실패, 재시도 성공, `server_id_mappings` 생성, 중복 큐 방지를 검증한다. 수동 검증은 `tmp/run-logs/`의 실행 로그와 공통 SQLite 이력을 보존한다.
