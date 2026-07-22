# WPF 사용자별 알림 cursor 보존 정책

이 문서는 2026-07-22 현재 `ServerNotificationCursorService`, `ServerEpochGuardService`, `ServerReconciliationService` 구현 기준이다.

WPF의 서버 채널 알림 polling 위치는 공통 로컬 SQLite의 `server_notification_cursors`에 저장한다. 키는 정규화한 서버 scope와 서버 로그인 `user_id`의 조합이다. 서버 scope는 URL의 scheme, IDN host, 명시 포트와 base path를 포함하며 query, fragment, 사용자 정보는 제외한다.

## 저장과 처리 원칙

- `server_notification_cursors`는 마지막 성공 cursor, 서버가 응답 헤더로 알린 현재 cursor, 초기 따라잡기 완료 여부, 상태와 갱신 시각을 보존한다.
- `server_notification_messages`는 같은 서버 scope와 사용자 안에서 처리 완료한 공개 `message_id`, cursor와 처리 시각을 보존한다. `(server_scope, user_id, message_id)`는 유일하다.
- WPF는 응답의 모든 항목을 처리하고 각 `message_id`를 기록한 뒤 같은 SQLite 트랜잭션에서 cursor를 전진시킨다. 처리 예외나 강제 종료로 트랜잭션이 완료되지 않으면 이전 cursor에서 다시 조회한다.
- 성공한 응답을 다시 받아도 `message_id`가 이미 있으면 처리 부작용을 반복하지 않는다. 현재 polling 처리 자체는 서버 읽음이나 receipt를 자동 변경하지 않으며, 읽음과 수신 확인은 사용자의 명시 동작으로 서버에 남긴다.
- 서버는 `X-FlowNote-Notification-Cursor` 응답 헤더로 현재 서버 high-water cursor를 알린다. 마지막 page까지 처리한 경우 WPF는 접근 권한이 없는 중간 ID를 포함한 high-water 위치까지 안전하게 전진한다.

## 전환과 복구 정책

- 사용자 전환: 새 `user_id` row를 사용한다. 이전 사용자의 cursor와 처리된 `message_id`는 유지하지만 공유하지 않는다.
- 서버 URL 변경: 정규화 결과가 다른 base URL이면 새 server scope row와 binding 후보를 사용한다. 이미 다른 binding이 있으면 새 URL을 자동 승인하지 않고 `RECONCILIATION_REQUIRED`로 차단한다. 기존 서버 cursor는 유지하며 새 서버와 공유하지 않는다.
- 로그아웃 또는 HTTP 401: polling을 즉시 중지하고 재로그인을 요구한다. cursor와 처리 이력은 삭제하거나 전진시키지 않는다. 같은 서버와 사용자로 재로그인하면 마지막 성공 cursor 다음부터 재개한다.
- 로컬 DB 복구: 복구 DB에 해당 row가 있으면 그대로 재개한다. row가 없으면 cursor 0에서 시작하고 화면에 `이전 알림을 재확인 중입니다. 중복 알림을 새로 만들지 않습니다.`와 진행 위치를 한글로 표시한다.
- 서버 DB 복구 또는 초기화: polling 전에 sync manifest의 instance/epoch와 `server_cursor`를 확인한다. 저장한 instance/epoch가 다르거나 manifest cursor가 로컬 마지막 성공 cursor보다 낮으면 binding을 `RECONCILIATION_REQUIRED`로 바꾸고 polling과 자동 전송을 함께 중지한다. cursor를 자동으로 0으로 되돌리지 않는다.
- 일반 cursor 초기화: 복구 경계가 아닌 경우 서버 상태를 확인한 `admin` 또는 `system-admin`만 주 창의 `알림 위치 초기화`에서 현재 서버 scope와 현재 사용자의 cursor를 0으로 초기화할 수 있다. 복구 경계가 감지된 동안에는 이 단독 초기화를 차단하고 `이력 > 서버 재결합` 승인을 요구한다.
- 재결합 적용: 관리자가 전체 큐 판정과 사유를 승인하면 현재 서버 scope의 모든 사용자 cursor를 한 로컬 transaction에서 0으로 바꾸고 `initial_sync_completed = 0`, 상태 `ACTIVE`로 재추적한다. 기존 처리 `message_id`는 삭제하지 않으며 binding의 승인 instance/epoch도 관측값으로 갱신한다.

첫 동기화가 100건 page를 넘으면 100ms 간격으로 다음 page를 이어 받고 `진행 위치: 현재/서버`를 표시한다. 따라잡기가 끝나면 기본 15초 polling으로 돌아간다. 연결 실패는 기존 정책대로 최대 120초까지 backoff한다.

## 검증 기준

- Core 단위 테스트는 두 사용자·두 서버 scope, 정상 처리, 처리 예외 rollback, 앱 재시작에 해당하는 서비스 재생성, 로그아웃/재로그인 보존, 로컬 DB 복구의 row 부재, 서버 cursor 역행, 일반 사용자 초기화 거부, 관리자 초기화 뒤 기존 `message_id` 멱등 보존과 401 불변 조건을 검증한다. instance/epoch 변경과 다른 정규화 URL 차단, 차단 중 큐 보존도 별도 guard 회귀 테스트로 검증한다.
- WPF 스모크는 공통 `data/local/flownote.local.sqlite`에 cursor와 `message_id`를 누적하고, 서버 `notification_channel_members.last_read_message_id` 및 `handover_receipts.receipt_status`와 함께 대조한다.
