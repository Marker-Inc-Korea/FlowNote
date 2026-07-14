# FlowNote 설계 결정

## 2026-06-30. 현재 문서 기준

- 문서는 현재 코드에 맞춰 작성한다.
- 아직 구현되지 않은 기능은 제품 방향 또는 후속 범위로 분리한다.
- 과거 일일 기록보다 `README.md`와 `docs/` 상위 문서를 최신 기준으로 본다.

## 2026-06-30. FieldComment 명칭

- 현장 코멘트 도메인 명칭은 `FieldComment`, `field_comments`, `field-comments`를 사용한다.
- `FieldNote`, `field_notes`, `field-notes`, `FIELD_NOTE`는 FlowNote 제품명과 혼선을 만들 수 있으므로 새 작업에 사용하지 않는다.
- 새 WPF 코멘트는 문서 버전이 아니라 `field_comments` 원천 이력으로 저장한다.
- 기존 공통 SQLite에 남아 있는 구 FieldNote 테이블과 큐 row는 테스트 이력으로 보존한다. 현재 WPF는 `field_note/register_field_note`, `field_note_attachment/register_field_note_attachment` 큐를 FieldComment API로 자동 변환하지 않고 별도 전환 또는 마이그레이션 검토 대상으로 분류한다.

## 2026-07-14. 보존 동기화 실패 무손실 전환

- FAILED 누적 큐의 진단은 구 create, 구 FieldNote/첨부, 선행 서버 ID 누락, 로컬 파일 누락, 실제 서버/인증 오류의 배타적 분류를 사용한다.
- 전환 상태는 `자동 전환 가능`, `관리자 확인 필요`, `원본 누락으로 전환 불가`, `계속 보존` 네 가지다.
- dry-run은 SQLite read-only 연결만 사용하고 원천 row, 대상 action, 예상 idempotency key와 안정된 plan hash를 출력한다.
- 승인 실행은 직전 plan hash와 명시한 원천 큐 row ID만 받는다. 기존 큐와 파일은 수정·삭제하지 않고 현재 action의 신규 큐와 `server_sync_migration_audit`를 추가한다.
- 구 FieldNote는 새 FieldComment/첨부 원천으로 복제하되 작성자, 시각, 본문, 첨부 메타데이터, 원천 ID와 `FieldNote` 구 명칭을 감사 snapshot으로 보존한다.
- 원천 큐 ID와 대상 idempotency key를 유일하게 연결해 같은 승인을 반복해도 신규 큐·매핑·감사 중복이 생기지 않게 한다.

## 2026-06-30. 사용자 관리

- WPF 사용자 관리는 `admin`, `system-admin` 역할만 사용할 수 있다.
- 사용자 관리 화면은 사용자 추가, 표시 이름 변경, 역할 변경, 비밀번호 변경을 지원한다.
- 새 사용자 ID는 `user-{loginId}`로 자동 생성한다.
- 로그인 ID는 소문자 정규화 후 영문/숫자/하이픈/밑줄/점만 허용한다.
- 사용자 생성과 수정은 `activity_history`에 `user.created`, `user.updated`로 기록한다.

## 2026-06-30. 문서 공개 버전

- 문서 업로드 또는 새 버전 등록은 자동 공개가 아니다.
- 문서 최신 버전과 공개 버전은 분리한다.
- 서버는 `documents.latest_version_id`와 `documents.published_version_id`를 분리한다.
- WPF는 `documents.version_no`와 `documents.published_version_no`를 분리한다.
- 공개하려면 명시적 publish 동작을 수행해야 한다.

## 2026-06-30. WPF 로컬 저장 우선

- WPF 앱은 서버 연결 여부와 관계없이 로컬 SQLite 저장을 먼저 성공시킨다.
- 서버 URL이 있으면 전송을 시도하고, 실패하면 `server_sync_queue`와 `activity_history`에 남긴다.
- 서버 ID는 `server_id_mappings`와 각 로컬 원천 테이블의 서버 ID/synced_at 컬럼에 기록한다.

## 2026-06-30. 서버 인증 세션

- FastAPI는 HMAC Bearer access token과 `auth_sessions` 테이블을 함께 사용한다.
- login은 세션을 만들고 access/refresh token을 반환한다.
- refresh는 같은 세션에서 access token ID와 refresh token hash를 회전한다.
- logout은 현재 세션을 `REVOKED`로 바꾼다.

## 2026-07-01. WPF와 서버 계정 정책

- WPF 사용자 추가, 역할 변경, 비밀번호 변경은 로컬 SQLite 계정 전용이다.
- 서버 계정 발급과 변경은 서버 DB 운영 절차에서 관리하며, WPF 서버 계정 관리 API 연동은 후속 범위로 둔다.
- 서버 로그인 성공 시 WPF 현재 세션은 서버 사용자 ID, 표시 이름, role을 우선 사용한다.
- 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.
- WPF 보고서 버튼은 FastAPI `ReportWriteUser`와 같은 role 집합만 활성화한다.

## 2026-07-02. 운영 초기 서버 계정

- 서버 DB 최초 생성 시 만들어지는 `admin` 계정을 최초 서버 관리자 계정으로 사용한다.
- 개발/스모크 테스트 기본 비밀번호 `1234`는 운영 로그인 전에 서버 PC에서 현장 비밀번호로 변경한다.
- 현재 구현 범위에서는 첫 로그인 후 비밀번호 변경을 앱이 강제하지 않는다. 운영 기준은 첫 로그인 전 비밀번호 변경이며, 강제 변경 컬럼/API/WPF 화면은 후속 범위다.
- 서버 계정의 발급, 비밀번호 재설정, 잠금, 비활성화, 퇴사 처리는 서버 DB 운영 스크립트로 수행하고 기존 활성 세션을 폐기한다.
- WPF 로컬 계정은 오프라인 또는 서버 미설정 상황의 로컬 계정이며 서버 계정의 대체 관리 화면이 아니다.

## 2026-07-06. 서버 계정 API와 WPF role 우선순위

- 운영 배포 전 단계에서는 서버 계정 관리 공개 API를 추가하지 않고 `app.ops.server_accounts` 운영 스크립트 기준을 유지한다.
- 첫 로그인 후 비밀번호 변경 강제는 `must_change_password` 컬럼, 변경 API, WPF 강제 변경 화면을 함께 설계해야 하므로 이번 범위에서는 착수하지 않는다.
- 서버 로그인 성공 시 WPF 화면 권한은 서버 응답 role을 우선한다. 같은 로그인 ID의 로컬 role은 서버 세션의 버튼 활성/비활성 계산에 사용하지 않는다.
- 서버가 로그인에 401 또는 403을 반환하면 WPF는 같은 ID의 로컬 계정으로 fallback하지 않는다. fallback은 서버 URL이 없거나 연결 자체가 실패한 경우에만 허용한다.
- 서버와 WPF의 role 집합과 권한표는 FastAPI `test_role_permissions_api.py`와 WPF 스모크의 `RolePermissionPolicy` 행렬로 함께 고정한다.

## 2026-07-06. AI 검색 기초 범위

- AI 계층의 첫 범위는 자동 조언이 아니라 근거가 있는 검색과 요약 후보 생성으로 제한한다.
- 검색 후보 원천은 공개 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source 네 종류만 사용한다.
- 후보는 `ai_search_candidates` read model에 저장하고, 원문 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source row로 돌아갈 수 있는 `source_*`와 `trace_*` 식별자를 함께 둔다.
- FieldComment가 `ANALYZED`, `REVIEWED`, `SELECTED` 상태로 충분히 쌓이기 전에는 AI 답변 품질보다 관리자 검토/분석/선정 운영 흐름 보강을 우선한다.
- MES/ERP 외부 연동 필드는 검색 후보 생성에 사용하지 않는다. `mes_integration` FieldComment도 어댑터 정책이 확정되기 전에는 후보에서 제외한다.

## 2026-07-07. AI 검색 운영 점검 흐름

- AI 검색 운영 점검 화면은 외부 AI 호출 없이 `ai_search_candidates` 재생성 결과와 품질 지표를 확인하는 범위로 둔다.
- 운영자는 공개 문서 버전, FieldComment, 작업순서 이력, 보고서 source별 후보 수와 제외 사유를 먼저 확인한다.
- 제외 사유는 공개 문서 미충족, FieldComment 보관/제외, MES 통합 입력, 빈 FieldComment, 텍스트 없는 작업순서 이력, 누락/보관/원천 누락 보고서 source로 구분하고 운영 조치 힌트를 함께 제공한다.
- 후보 row는 `source_id`, `source_version_id`, `trace_table`, `trace_id`, `trace_version_id`로 원문 문서 버전, FieldComment, 작업순서 이력, 보고서 source row까지 역추적되어야 한다.
- WPF 운영 점검 화면은 서버의 후보 재생성/품질/목록 API를 호출하고, 선택한 후보의 추적값을 운영자가 복사해 원천 row 확인에 사용할 수 있게 한다.
- 자동 답변 생성, 자동 의사결정, 작업지시 자동 변경은 이번 운영 점검 범위에 포함하지 않는다.

## 2026-07-01. WPF 보고서 저장 흐름

- WPF 보고서 창은 FieldComment, 문서, 작업순서 이력을 보고서 근거 후보로 사용한다.
- WPF 보고서 저장은 로컬 보고서 문서와 `report_sources`를 먼저 만든 뒤 서버 `/api/v1/reports` 저장을 시도한다.
- 보고서 저장 실패는 보고서 전용 큐를 새로 만들지 않고 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남긴다.
- 큐에는 한글 실패 사유, 마지막 시도 시간, 시도 횟수를 기존 동기화 항목과 같은 방식으로 기록한다.
- 서버 재시도 중복 방지는 `/api/v1/reports`의 `idempotencyKey`와 WPF `wpf:report:{localReportDocumentId}` 키로 처리한다.
- 서버 보고서 저장에 성공한 로컬 보고서 문서는 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`에 연결한다.

## 2026-07-02. 서버-WPF 문서 동기화 우선순위

- WPF는 로컬 저장을 먼저 성공시키고 `server_sync_queue` 재시도 시 같은 문서 또는 보고서 근거 단위의 선행 조건을 우선한다.
- 재시도 처리 순서는 문서 등록, 문서 버전, 문서 공개, 문서 상태, FieldComment, FieldComment 검토, FieldComment 첨부, 접근 로그 시작/종료/자동 종료/다운로드 차단, 보고서 저장이다.
- 선행 문서, 문서 버전, FieldComment, 보고서 근거의 서버 ID가 없으면 해당 큐는 실제 서버 호출 없이 보류로 분류하고 `attempt_count`를 증가시키지 않는다.
- 문서 최초 등록이 서버 ID를 받아야 문서 버전, FieldComment, 첨부, 접근 로그가 서버 문서/버전 ID에 연결된다.
- 문서 최신 버전은 로컬 `document_versions.version_no` 기준으로 서버 버전을 찾고, 서버에 같은 번호가 있으면 매핑을 복구하며 없으면 업로드한다.
- 공개 버전은 해당 로컬 버전의 서버 버전 ID가 있을 때만 서버 publish API에 반영한다.
- 문서 상태는 현재 로컬 `documents.status`를 서버에 반영한다. `PUBLISHED` 상태는 공개 버전 동기화가 선행되어야 한다.
- 서버 미동작, 인증 만료, 선행 문서/버전 미동기화 상황에서도 로컬 데이터와 큐는 삭제하지 않는다.
- 작업순서 보드/항목/이력은 현재 단계에서 WPF 로컬 큐 대상이 아니다. 서버 직접 API 검증과 보고서 source 추적 범위로 유지한다.

## 2026-06-30. 관리자 파일 감시

- 파일 감시는 WPF 네이티브 `FileSystemWatcher` 기반 로컬 기능이다.
- `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 사용할 수 있다.
- 감지된 파일은 즉시 업로드하지 않고 `file_watch_candidates`에 `PENDING`으로 저장한다.
- 확정 시 대상 문서, 버전명, 변경 사유가 필요하며 새 `document_versions` row를 만든다.

## 2026-07-02. Windows 운영 배포 방식

- WPF 클라이언트 설치파일은 MSI를 기준으로 한다.
- MSI 설치 위치는 `C:\Program Files\FlowNote\Client\FlowNote.Windows.App`이며 로컬 SQLite와 `Files`는 `FLOWNOTE_LOCAL_DATA_DIR` 아래에 분리한다.
- MSIX는 서명, 패키지 아이덴티티, 앱 컨테이너 제약을 현장별로 더 검토해야 하므로 초기 기준에서 제외한다.
- FastAPI 서버 상시 실행은 Windows 작업 스케줄러 `\FlowNote\FlowNoteApi` 작업으로 등록한다.
- 작업 스케줄러는 Windows 기본 기능만으로 부팅 시 실행, 수동 시작, 중지, 재시작, 로그 남김을 처리할 수 있어 초기 서버 PC 배포 기준에 맞다.
- Windows Service 직접 등록은 Python/FastAPI 프로세스용 서비스 래퍼 또는 별도 호스트 구현이 필요하므로 후속 선택지로 둔다.
- 현재 저장소에는 `package-wpf-msi.ps1`, `install-flownote-server-task.ps1`, `manage-flownote-server-task.ps1`, `run-flownote-server.ps1`가 있으며, 운영 현장 적용 전에는 MSI 설치 검증, 서명, 런타임 포함 여부를 별도로 확인한다.

## 2026-07-06. WPF MSI 런타임과 서명 기준

- `package-wpf-msi.ps1`의 기본 산출물은 framework-dependent MSI다. 설치 대상 PC에 대상 버전의 `.NET Windows Desktop Runtime`이 보장되지 않으면 `-SelfContained` MSI를 별도 생성한다.
- self-contained MSI는 .NET 런타임 파일을 포함하지만 WebView2 Evergreen Runtime은 포함하지 않는다. WebView2 Runtime은 설치 전 별도 점검과 설치 절차로 관리한다.
- MSI 파일 세트에는 WPF 실행 파일, `.deps.json`, `.runtimeconfig.json`, 앱 DLL, 의존 DLL, 네이티브 DLL만 포함한다. 로컬 SQLite, WAL/SHM, `Data`/`Files`, 테스트 산출물, 고객 파일 패턴이 publish 파일 세트에 있으면 패키징을 실패시킨다.
- framework-dependent와 self-contained MSI를 번갈아 만들 때 publish 폴더의 이전 파일이 섞이지 않도록 `package-wpf-msi.ps1`는 publish 폴더를 비운 뒤 새로 생성한다.
- 설치 후에는 `verify-wpf-msi-install.ps1`로 MSI 파일 목록 금지 패턴, 설치 폴더와 로컬 데이터 폴더 분리, .NET Desktop Runtime, WebView2 Runtime, 선택적 서명 검증을 확인한다.
- 운영 배포 MSI는 코드 서명 인증서로 서명하는 것을 기준으로 한다. 서명 시 publish된 `FlowNote.Windows.App.exe`를 먼저 서명하고, 그 EXE가 포함된 MSI를 생성한 뒤 최종 MSI도 서명하고 검증한다.
- 미서명 MSI는 내부 임시 검증용으로만 허용하며, 배포 대상, MSI 해시, 승인자, Windows 경고 안내를 운영 기록에 남긴다.

## 2026-07-02. 운영 백업/복구와 후속 계층 착수 기준

- 서버 SQLite, 서버 `storage`, 서버 `.env`/로그는 서버 운영 백업 세트로 관리한다.
- WPF 로컬 SQLite와 WPF `Files`는 PC별 로컬 백업 세트로 관리한다.
- 서버 DB와 서버 `storage`는 같은 시점의 백업을 정상 복구 기준으로 삼는다. DB만 또는 `storage`만 복원한 상태는 정상 운영 재개가 아니라 장애 대응 상태다.
- 복구 검증은 서버 health, DB health, WPF 로그인, 문서 목록, 문서 열람, FieldComment, 보고서 근거 조회를 포함한다.
- 복구 후 가능한 환경에서는 `.\scripts\verify-preserved-tests.ps1` 또는 동등 운영 점검을 실행한다.
- 외부 AI 호출 기반 검색/작업 조언은 공개 문서, FieldComment, 보고서, 작업순서 이력이 충분히 축적되고 근거 역추적이 가능해진 뒤 후속 계층으로 착수한다. 현재 구현은 `ai_search_candidates` 근거 후보 운영과 외부 호출 전 비활성·승인·목적·snapshot·감사 차단 골격까지이며 운영 provider 연동은 하지 않는다.
- MES/ERP 어댑터는 후속 연동 대상이며, 초기 수동 작업지시의 `work_order_no`, 문서 연결, 작업순서, FieldComment, 보고서 근거와 연결되는 방식으로 설계한다.

## 제품 범위 결정

- FlowNote는 MES/ERP를 대체하지 않는다.
- 문서 구조는 고객이 결정한다.
- BOM 문서 구조는 현장 표현 예시이며 기본 강제 구조가 아니다.
- 외부 AI 호출 기반 검색과 작업 조언은 충분한 데이터 축적 뒤 후속 기능으로 둔다.
- 초기 배포는 서버 PC 1대와 Windows 설치형 클라이언트를 기준으로 하되, 제품 클라이언트 범위에는 Android 현장 단말 앱을 포함한다.

## 2026-07-07. 설치형 클라이언트와 채널 알림

- Windows WPF는 관리자/현장 PC의 문서 운영, 파일 감시, 보고서 정리, 로컬 저장 보강, 채널 감독, 인수인계 관리를 담당한다.
- Android 앱은 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세 메타데이터 확인, FieldComment, 사진 기록, 신호등식 상태 기록, 인수인계 확인, 채널 알림을 담당한다. 현재 문서 파일 본문 뷰어와 인수인계 신규 작성 화면은 구현 범위에 들어오지 않았다.
- Windows와 Android 알림은 개인 메신저나 사내 메신저 대체가 아니라 업무 채널 모델로 설계한다.
- 채널은 라인, 설비, 공정, 작업조, 작업내역, 인수인계 같은 운영 단위에 연결한다.
- 인수인계는 채널에 등록되는 업무 이벤트이며 수신자는 확인, 보류, 후속 FieldComment 작성 같은 상태를 남긴다.
- 개인 휴대폰 기본 배포, 개인 메신저 수집, GPS 추적, 근태 관리는 초기 범위에 포함하지 않는다.

## 2026-07-09. 서버 공통 채널과 인수인계 모델

- FastAPI 서버는 `notification_channels`, `notification_channel_members`, `channel_messages`, `handovers`, `handover_receipts`를 Windows와 Android가 공유하는 채널/인수인계 원천 모델로 둔다.
- 사용자별 알림은 별도 개인 DM 테이블이 아니라 채널 멤버십과 `channel_messages` 읽음 위치로 계산한다.
- 채널 메시지와 인수인계는 문서, FieldComment, 작업순서 항목/이력, 작업내역, 보고서, 인수인계 원천 ID를 보존한다.
- 인수인계 receipt는 수신자별 `UNREAD`, `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED`를 기록한다.
- 서버 API는 채널 멤버 또는 `admin`, `system-admin`만 채널 메시지와 인수인계를 조회할 수 있게 한다.
- 개인 DM, 개인 메신저 수집, GPS, 근태 기능은 서버 채널/인수인계 모델에 포함하지 않는다.

## 2026-07-13. 사내망 polling을 채널·인수인계 알림의 1차 전달 방식으로 확정

- 서버 PC와 승인된 설치형 단말이 같은 사내망에서 동작하는 초기 배포는 HTTP polling을 1차 알림 전달 방식으로 사용한다.
- `/api/v1/notifications`의 단조 증가 `cursor`와 `afterId`를 사용해 마지막 성공 위치 다음부터 오름차순으로 조회한다. 클라이언트는 `message_id`와 cursor를 멱등 키로 사용하며, cursor는 응답을 처리한 뒤에만 전진시킨다.
- Windows와 Android 전경 상태는 기본 15초 주기로 확인한다. 연결 실패 시 30초, 60초, 최대 120초까지 지수 백오프하고 성공 즉시 15초로 복귀한다. 서버 또는 네트워크 복구 뒤에는 현재 보유한 마지막 cursor부터 재개한다.
- HTTP 401이면 polling을 중지하고 재로그인을 요구한다. Android는 사용자별 cursor를 `SharedPreferences`에 보존해 다른 사용자와 공유하지 않는다. 현재 WPF는 주 창 세션 메모리에만 cursor를 유지하므로 새 창 세션은 0부터 다시 따라잡으며, 사용자별 영구 보존은 후속 보강 대상이다.
- Windows는 창이 열린 동안만, Android는 Activity가 전경인 동안만 15초 polling한다. 비활성·종료 상태에는 즉시 polling을 중단한다.
- Android 백그라운드 확인은 1차 구현에 상시 서비스를 두지 않는다. WorkManager를 도입하더라도 현장 단말 정책이 허용하는 네트워크 연결 조건의 제한된 주기 작업으로만 사용하며, Android 최소 주기·Doze·배터리 최적화로 즉시성이 보장되지 않음을 운영 문서에 표시한다.
- WebSocket은 프록시, 재연결, 서버 fan-out 운영 기준이 마련된 뒤의 사내망 저지연 선택지다. FCM 등 외부 push는 인터넷 연결과 외부 전송 보안 정책을 별도 승인한 현장의 후속 선택지다.

## 2026-07-09. Android 현장 단말 최소 앱

- Android 현장 앱은 Java, Android 네이티브 View, Gradle Android plugin을 최소 기술 스택으로 시작한다.
- 최소 OS는 Android 8.0(API 26)으로 둔다. 초기 현장 대상은 승인된 태블릿 또는 러기드 단말이며 개인 휴대폰 기본 배포는 제외한다.
- 패키지는 `com.flownote.fieldapp`를 사용한다.
- Android 로그인은 서버 `/api/v1/auth/login`에 `deviceId`를 보내며, 서버 `terminal_devices.status = ACTIVE`인 승인 단말만 세션을 받을 수 있다.
- 서버 세션은 Android 승인 단말 ID를 `auth_sessions.device_id`에 보존한다.
- Android 로컬 저장은 장기 원천 DB가 아니라 FieldComment와 사진 첨부 재전송용 outbox로 제한한다.
- FieldComment 재전송은 `android:{deviceId}:{localId}` idempotency key를 사용해 서버 중복 생성을 막는다.
- 채널 알림과 인수인계는 새 개인 메시지 체계가 아니라 서버 공통 채널/인수인계 API 조회, 읽음, 수신확인으로 붙인다.
- GPS 추적, 근태 관리, 개인 메신저 수집, 사내 메신저 전체 대체는 Android 앱 초기 범위에 포함하지 않는다.

## 2026-07-10. 승인 단말 운영 상태와 교체 이력

- 승인 단말 상태는 `ACTIVE`, `INACTIVE`, `RETIRED`로 통일한다. `RETIRED`는 폐기·교체 완료 상태이므로 재활성화하지 않는다.
- 단말 관리 API와 WPF 운영 화면은 서버 계정 `admin`, `system-admin`만 사용한다.
- 교체는 기존 단말을 `RETIRED`로 변경하고 새 단말을 등록하는 하나의 서버 트랜잭션으로 처리한다.
- 단말 등록자, 마지막 변경자, 대체한 기존 device ID를 `terminal_devices`에 보존하고 등록·변경·상태·교체 이벤트는 `activity_history`에 남긴다.
- Android 로그인 성공 때마다 `terminal_devices.last_seen_at`을 갱신하고 각 로그인 세션의 `auth_sessions.device_id`를 유지한다.

## 2026-07-10. 외부 AI 1단계 안전장치와 API 계약

- 외부 AI 첫 범위는 `EVIDENCE_SEARCH`, `EVIDENCE_SUMMARY`로 제한한다. 자동 의사결정, 작업지시 생성·변경, 승인·공개 자동화, 설비 제어, 안전·품질 판정은 금지한다.
- 외부 호출은 기본 비활성화하고 고객·현장별 운영자 승인과 기능 플래그를 모두 요구한다. 내부 `PUBLISHED` 상태를 외부 전송 동의로 해석하지 않는다.
- 응답의 모든 사실 주장은 질의 시점 `ai_search_candidates` snapshot에 있는 문서 버전, FieldComment, 작업순서 이력 또는 `report_sources.id` 인용을 가져야 한다. 근거 부족이나 인용 검증 실패 시 답변 본문을 반환하지 않는다.
- `ai_queries`, `ai_query_evidence_candidates`, `ai_query_citations`, `ai_prompt_versions`, `ai_call_attempts`, `ai_transfer_approvals` 안전장치 골격을 구현한다. 응답은 기본 미저장, 질의 원문과 승인 저장 응답은 90일, 근거·인용·호출·오류·승인 감사 메타데이터는 1년 보존한다.
- 재생성은 보존 중인 질의, 불변 프롬프트 버전, 근거 snapshot과 provider/model을 다시 사용하되 동일 문구를 보장하지 않는다. 원천 권한·상태·승인이 바뀌면 재생성하지 않는다.
- 민감정보와 고객 문서의 외부 전송 금지·최소화·승인·철회 절차는 [보안 문서](./security.md#외부-ai-전송과-운영자-승인)를 단일 운영 기준으로 사용한다.
- 이 결정은 운영 provider client나 네트워크 호출을 활성화하지 않는다. 주입 가능한 테스트 경계만 두며 기존 `ai_search_candidates` read model과 후보 API는 기능 플래그에 의존하지 않고 현재 테스트 계약을 유지한다.

## 2026-07-13. 외부 AI 착수 전 ground-truth 회귀 게이트

- 후보 ID는 source type/id/version의 결정적 hash로 만들고 검색 본문의 별도 `content_hash`를 둬 재생성 전후 동일 원천을 비교한다.
- 사람형 스모크와 API 테스트는 문서 버전, FieldComment, 작업순서 변경 이력, 보고서 source가 함께 필요한 질문과 기대 candidate/source/version/trace ID를 저장한다.
- 삭제·비공개 문서, 제외/보관 FieldComment, 사라진 보고서 원천, 권한 없는 채널, 근거 부족 질문을 부정 사례로 유지하며 근거 부족은 `INSUFFICIENT_EVIDENCE`로 판정한다.
- provider 착수 지표는 평가 전건 통과, 네 원천 유형 커버, candidate ID/content hash와 순위 재현성, 검토 완료 FieldComment 100건 충족을 모두 요구한다. 이 지표는 운영 승인과 기능 플래그를 대신하지 않으며 외부 호출을 자동 활성화하지 않는다.

## 2026-07-13. controlled copy는 짧은 만료의 1회성 인증 스트리밍 사용

- 사내 서버 운영의 controlled copy는 일반 정적 파일 URL이나 로컬 원본 복사가 아니라 기본 60초의 1회성 티켓 발급 후 인증 스트리밍으로 제공한다.
- 티켓은 사용자와 로그인 세션, 선택한 문서/버전에 묶고 원문 대신 SHA-256만 DB에 저장한다. 다른 사용자·세션, 만료, 재사용, Range 요청은 차단한다.
- controlled copy 대상은 삭제되지 않은 현재 `PUBLISHED` 문서의 정확한 공개 버전 하나로 제한한다. 저장 경로 경계, 크기 제한, 파일 SHA-256은 발급과 전송 시점에 다시 검사한다.
- 요청·허용·완료·실패·차단은 `document_access_logs`와 `activity_history`에 사용자, 세션 단말, 문서 버전, 접속 정보, 사유와 함께 남긴다. 존재하지 않는 문서 요청은 문서 외래키가 없으므로 `activity_history`에 남긴다.
- WPF 허용 role 버튼은 서버 API와 서버 ID 매핑을 사용하고 비허용 role은 기존 로컬 차단 안내와 접근 로그 흐름을 유지한다.
