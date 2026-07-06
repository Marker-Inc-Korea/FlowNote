# FlowNote 설계 결정

## 2026-06-30. 현재 문서 기준

- 문서는 현재 코드에 맞춰 작성한다.
- 아직 구현되지 않은 기능은 제품 방향 또는 후속 범위로 분리한다.
- 과거 일일 기록보다 `README.md`와 `docs/` 상위 문서를 최신 기준으로 본다.

## 2026-06-30. FieldComment 명칭

- 현장 코멘트 도메인 명칭은 `FieldComment`, `field_comments`, `field-comments`를 사용한다.
- `FieldNote`, `field_notes`, `field-notes`, `FIELD_NOTE`는 FlowNote 제품명과 혼선을 만들 수 있으므로 새 작업에 사용하지 않는다.
- 새 WPF 코멘트는 문서 버전이 아니라 `field_comments` 원천 이력으로 저장한다.

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

## 2026-07-01. WPF 보고서 저장 흐름

- WPF 보고서 창은 FieldComment, 문서, 작업순서 이력을 보고서 근거 후보로 사용한다.
- WPF 보고서 저장은 로컬 보고서 문서와 `report_sources`를 먼저 만든 뒤 서버 `/api/v1/reports` 저장을 시도한다.
- 보고서 저장 실패는 보고서 전용 큐를 새로 만들지 않고 기존 `server_sync_queue`에 `entity_type = report`, `action = register_report`로 남긴다.
- 큐에는 한글 실패 사유, 마지막 시도 시간, 시도 횟수를 기존 동기화 항목과 같은 방식으로 기록한다.
- 서버 재시도 중복 방지는 `/api/v1/reports`의 `idempotencyKey`와 WPF `wpf:report:{localReportDocumentId}` 키로 처리한다.
- 서버 보고서 저장에 성공한 로컬 보고서 문서는 `documents.server_report_id`, `documents.server_document_id`, `document_versions.server_version_id`, `server_id_mappings`에 연결한다.

## 2026-07-02. 서버-WPF 문서 동기화 우선순위

- WPF는 로컬 저장을 먼저 성공시키고 `server_sync_queue` 생성 순서대로 서버에 반영한다.
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
- 운영 배포 MSI는 코드 서명 인증서로 서명하는 것을 기준으로 한다. 서명 시 publish된 `FlowNote.Windows.App.exe`를 먼저 서명하고, 그 EXE가 포함된 MSI를 생성한 뒤 최종 MSI도 서명하고 검증한다.
- 미서명 MSI는 내부 임시 검증용으로만 허용하며, 배포 대상, MSI 해시, 승인자, Windows 경고 안내를 운영 기록에 남긴다.

## 2026-07-02. 운영 백업/복구와 후속 계층 착수 기준

- 서버 SQLite, 서버 `storage`, 서버 `.env`/로그는 서버 운영 백업 세트로 관리한다.
- WPF 로컬 SQLite와 WPF `Files`는 PC별 로컬 백업 세트로 관리한다.
- 서버 DB와 서버 `storage`는 같은 시점의 백업을 정상 복구 기준으로 삼는다. DB만 또는 `storage`만 복원한 상태는 정상 운영 재개가 아니라 장애 대응 상태다.
- 복구 검증은 서버 health, DB health, WPF 로그인, 문서 목록, 문서 열람, FieldComment, 보고서 근거 조회를 포함한다.
- 복구 후 가능한 환경에서는 `.\scripts\verify-preserved-tests.ps1` 또는 동등 운영 점검을 실행한다.
- AI 검색/작업 조언은 공개 문서, FieldComment, 보고서, 작업순서 이력이 충분히 축적되고 근거 역추적이 가능해진 뒤 후속 계층으로 착수한다.
- MES/ERP 어댑터는 후속 연동 대상이며, 초기 수동 작업지시의 `work_order_no`, 문서 연결, 작업순서, FieldComment, 보고서 근거와 연결되는 방식으로 설계한다.

## 제품 범위 결정

- FlowNote는 MES/ERP를 대체하지 않는다.
- 문서 구조는 고객이 결정한다.
- BOM 문서 구조는 현장 표현 예시이며 기본 강제 구조가 아니다.
- AI 검색과 작업 조언은 충분한 데이터 축적 뒤 후속 기능으로 둔다.
- 초기 배포는 서버 PC 1대와 Windows 설치형 클라이언트를 기준으로 한다.
