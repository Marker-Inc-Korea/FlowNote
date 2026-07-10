# 서버 동기화 실패와 재시도 UX

## 화면 기준

서버 동기화 상태는 기존 `이력` 창을 확장해 확인한다. 창 안에는 `활동 이력`과 `동기화 큐` 탭을 둔다.

`동기화 큐` 탭은 다음 컬럼을 표시한다.

화면 상단 요약의 대기, 실패, 보류, 완료 수는 목록 표시 한도와 관계없이 SQLite 전체 큐를 집계한다. 목록에는 현재 최대 500건을 표시하며, 요약에 전체 건수와 실제 표시 건수를 함께 보여준다.

- `상태`: `대기`, `실패`, `완료`
- `우선순위`: 운영자가 먼저 확인할 순서. `10 설정 필요`, `11 로그인 필요`, `12 연결 확인`, `20 파일 확인`, `30 문서 먼저`, `31 버전 먼저`, `32 FieldComment 먼저`, `33 근거 먼저`, `50 재시도`, `80 별도 정리`, `81 별도 전환`, `90 완료`
- `분류`: 서버 URL 미설정, 인증 만료, 네트워크 실패, 로컬 파일 누락, 선행 문서 미동기화, 선행 문서 버전 미동기화, 선행 FieldComment 미동기화, 보고서 근거 미동기화, 구 FieldNote 큐, 구 형식 큐, 실제 서버 오류, 재시도 가능, 완료
- `대상`: 문서, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 접근 로그, 보고서
- `작업`: 문서 전송, 버전 전송, 공개 전송, 상태 전송, FieldComment 전송, 검토 변경 전송, 첨부 전송, 열람 시작/종료/자동 종료/다운로드 차단 전송, 보고서 서버 저장
- `시도`: 서버 전송 시도 횟수
- `마지막 시도`: 마지막 재시도 시간
- `조치`: 운영자가 먼저 할 일
- `실패 사유`: 사용자가 조치할 수 있는 한글 실패 문구

`재시도` 버튼은 현재 `PENDING`, `FAILED` 큐를 다시 전송한다. 서버 URL 또는 로그인 토큰이 없으면 재시도하지 않고 “서버 URL 또는 로그인 정보가 없어 재시도할 수 없습니다. 서버 설정과 로그인을 확인하세요. 로컬 데이터는 삭제되지 않습니다.”를 표시한다.

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

문서 버전은 로컬 `document_versions.version_no`를 기준으로 서버 버전을 찾는다. 서버에 같은 번호의 버전이 이미 있으면 중복 업로드하지 않고 로컬 `server_version_id`, `synced_at`, `server_id_mappings`를 복구한다. 없으면 로컬 파일을 서버 버전으로 등록한다.

공개는 항상 특정 로컬 버전 번호의 서버 버전 ID가 확인된 뒤 서버 publish API를 호출한다. 문서 상태는 현재 로컬 `documents.status`를 서버 상태 API에 반영한다. 상태가 `PUBLISHED`이면 공개 대상 버전의 서버 버전 ID가 먼저 있어야 한다.

보고서 서버 저장은 로컬 보고서 문서와 `report_sources`를 먼저 남긴 뒤 `/api/v1/reports` 저장을 시도한다. 성공하면 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`를 연결한다. 실패하면 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남기고, 재시도 시 같은 idempotency key로 서버 저장을 다시 시도한다.

작업순서 보드/항목/이력은 현재 단계에서 WPF 로컬 큐의 양방향 동기화 대상이 아니다. 서버 연동 스모크는 서버 작업순서 API의 생성, 순서 변경, 상태 변경, 이력, 알림 후보를 직접 검증하고, WPF 보고서는 작업순서 항목/이력을 report source로 추적한다.

## 앱 시작 자동 재시도

앱 시작 시 서버 클라이언트가 구성되어 있으면 `RetryPendingAsync`를 한 번 실행한다. 결과 요약은 메인 화면 하단 상태 표시줄에 표시한다. 세부 시도, 실패, 성공은 `activity_history`와 `동기화 큐` 탭에서 확인한다.

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

후속 FastAPI 연동 스모크까지 실행한 최종 누적은 `SYNCED` 609건, `FAILED` 589건, `PENDING` 0건이다. 구 형식 create 300건은 모두 `attempt_count = 0`을 유지했고, `server_id_mappings` 767건의 중복 그룹은 0건이다.

현재 `server_id_mappings`는 648건이며 문서, 문서 버전, 공개, 상태, 접근 로그, FieldComment, FieldComment 검토, 첨부, 보고서 매핑이 남아 있고 정리 후에도 `(entity_type, local_id, local_version_no)` 중복 그룹은 0건이다. 이미 서버에 존재하는 문서 버전은 `document_versions.version_no`로 서버 버전을 찾아 `server_version_id`, `synced_at`, `server_id_mappings`를 복구하고 중복 업로드하지 않는다. 큐 재등록도 `idempotency_key` 유니크 제약과 `ON CONFLICT(idempotency_key)`로 중복 행을 만들지 않는다.

운영 우선순위는 다음 순서로 본다.

1. 서버 URL, 로그인, 네트워크 문제를 먼저 조치한다.
2. 로컬 파일 누락 문서는 파일 위치를 복구한다.
3. 같은 문서의 `document/register_document`를 먼저 동기화한다.
4. 같은 문서의 `document_version/register_document_version`과 `document_publish/publish_document_version`을 처리한다.
5. FieldComment를 먼저 동기화한 뒤 첨부, 검토 변경, 접근 로그를 재시도한다.
6. 구 FieldNote 큐는 자동 재시도 대상에서 분리해 관리자 전환 작업으로 다룬다.

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

WPF 스모크 테스트는 서버 미설정 실패, 재시도 성공, `server_id_mappings` 생성, 중복 큐 방지를 검증한다. 수동 검증은 `tmp/run-logs/`의 실행 로그와 공통 SQLite 이력을 보존한다.
