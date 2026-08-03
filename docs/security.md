# FlowNote 보안

이 문서는 2026-08-01 현재 코드에 적용된 통제와 운영 전 후속 통제를 구분한다.

## 현재 구현

현재 코드에 구현된 보안 기능은 다음과 같다.

- WPF 시작 시 로그인 요구
- WPF 로컬 계정 상태 `ACTIVE` 확인
- WPF role 기반 문서 등록, 파일 감시, 사용자 관리, 다운로드 허용 제어
- Windows 문서 뷰어 수동 닫힘과 열람 종료 감사
- 다운로드 차단 시 로컬 접근 로그와 활동 이력 기록
- FastAPI 로그인, access token, refresh token, logout
- FastAPI `auth_sessions` 기반 세션 폐기와 token 교체 검증
- FastAPI 서버 계정 생성·role/상태 변경·임시 비밀번호 재설정·세션 조회/폐기 API와 변경 사유 감사
- WPF 서버 계정 운영 화면과 `must_change_password` 로그인 직후 비밀번호 변경 강제
- FastAPI role 기반 문서 쓰기, 태그 생성, FieldComment 작성, 접근 로그 조회, 보고서 작성 권한
- 서버 PC 1대의 단일 고객·현장 경계와 다른 scope 입력을 `404`로 거부하고 `activity_history`에 남기는 fail-closed 검사
- FieldComment 원천 핵심 필드의 ORM 수정·삭제 차단, 원천 SHA-256 snapshot과 관리자 검토 전후 감사, 검토 revision 조건부 갱신·mutation receipt, 첨부 부모/파일 SHA-256 검증
- 위험 신호·상충 FieldComment의 분석자와 결정자 분리, 보고서 source version/hash 저장 직전 재검증과 report revision·내용/source 집합 hash·mutation receipt의 단일 transaction 저장
- 보고서 목록·상세·source 조회 시 모든 원천의 현재 상태·채널 멤버십 재검사, 권한 밖 보고서 비노출과 허용·거부 감사
- FastAPI 공개 문서 버전 controlled copy 1회성 티켓, 사용자·세션 바인딩, 만료·재사용 차단, 경로·크기·SHA-256 검증과 전체 감사
- FastAPI 채널 멤버십 기반 채널 메시지 조회, 사용자별 알림 읽음, 인수인계 수신 확인 권한
- Android 승인 단말 `deviceId` 로그인 검증과 `auth_sessions.device_id` 기록
- FastAPI 관리자 승인 단말 등록·상태·교체 API와 WPF 승인 단말 운영 화면
- WPF 채널함, 채널 관리, 인수인계 확인 현황 화면의 서버 인증/멤버십 기반 조회와 상태 변경
- Android 현장 단말 앱의 Keystore 보호 Bearer token, AES-GCM FieldComment·사진·인수인계 outbox 본문·첨부, 승인 단말 전용 1회성 보안 본문 열람, foreground 알림 복구, 인수인계 작성·확인, 서버 오류 원문 비노출
- 외부 AI 질의의 보고서 작성 role(`admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`) 제한, 기본 비활성 플래그, 허용 목적, 고객·현장·provider·model 전송 승인, 승인된 프롬프트와 근거 원천 상태 검사
- 외부 AI 질의·근거 snapshot·인용·호출 시도 감사 row, 기본 응답 본문 미저장과 응답 hash 저장
- `system-admin` 전용 외부 AI 전송 승인·불변 프롬프트 수명주기·고객/현장별 민감정보 정책 수명주기·전역/현장 kill switch와 한도·보존 정책 API 및 WPF 운영 화면
- 질의·응답·비밀 원문을 제외한 AI 운영 감사 조회/정책 허용 CSV와, 만료 질의 payload 비식별화·응답 원문 삭제의 자동·즉시 보존 처리 감사

Android 현장 단말과 Windows/Android 채널 화면은 현재 최소 구현이 들어와 있다. Android 문서 기능은 공개 목록·상세 조회와 PDF/이미지/UTF-8 TXT 앱 내부 보안 열람을 제공한다. 공통 채널 API는 서버 로그인, role, 채널 멤버십으로 접근을 제한하며, Android 로그인·모든 access 요청·refresh와 본문 열람은 세션의 `terminal_devices.device_id`와 `status = ACTIVE`를 요구한다. 승인 단말 등록, 비활성화, 폐기, 교체는 `admin`, `system-admin` 전용 API와 WPF 운영 화면에서 수행하고 `activity_history`에 변경 주체와 사유를 남긴다. Android 화면은 예외 메시지와 서버 오류 본문을 그대로 노출하지 않고 현장 사용자를 위한 한글 안내로 변환한다. Android는 개인 휴대폰 기본 배포가 아니라 승인된 현장 태블릿 또는 러기드 단말을 기준으로 한다. MDM 제품·운영 인증서·실단말 정책 보고서는 현장별 승인 범위다.

## 계정과 role

개발/스모크 테스트용 기본 비밀번호는 `1234`이다. 운영 배포에서는 이 값을 그대로 쓰면 안 된다.

운영 계정 기준:

- 서버 최초 관리자 계정은 서버 DB 초기화 시 생성되는 `admin` 계정이다.
- 운영 설치에서는 WPF 첫 서버 로그인 전에 서버 PC에서 `admin`의 비밀번호를 현장 비밀번호로 변경한다.
- 서버 로그인한 `admin`, `system-admin`은 WPF 서버 계정 화면과 `/api/v1/server-accounts`를 사용한다. 계정 생성과 비밀번호 재설정은 8자 이상 임시 비밀번호와 필수 변경 사유를 받고 `must_change_password = true`로 저장한다.
- `must_change_password = true`인 사용자는 로그인 직후 WPF 비밀번호 변경 화면으로 이동하며, 서버도 변경 API 이외의 보호 API와 refresh를 거부한다. 변경 성공 시 모든 활성 세션을 폐기하고 새 비밀번호 재로그인을 요구한다.
- 서버 DB 운영 스크립트는 최초 관리자 변경과 비상 운영 경로로 유지한다. 스크립트는 대화식 비밀번호 입력을 사용하고 8자 미만 비밀번호를 거부하지만 API와 달리 임시 비밀번호 강제 변경 플래그를 설정하지 않으므로 일반 계정 운영은 WPF/API를 우선한다.
- 로컬 로그인에서 여는 WPF 사용자 관리 화면은 로컬 SQLite 계정 전용이다. 서버 계정 화면과 로컬 계정 화면은 서로의 계정을 변경하지 않는다.
- 서버 URL이 설정된 WPF에서는 401·403뿐 아니라 인증서·주소·방화벽·시간 초과 오류에서도 로컬 계정 로그인으로 자동 우회하지 않는다. 서버 URL이 없는 승인된 로컬 운영 PC에서만 로컬 계정을 사용한다.

운영 전 비밀번호 변경 체크리스트:

- 서버 PC에서 `app.ops.server_accounts reset-password --username admin`으로 최초 서버 관리자 비밀번호를 변경한다.
- 새 비밀번호는 대화식 프롬프트에만 입력하고 명령줄 인자, 운영 기록, 로그에 적지 않는다.
- 변경 후 WPF 서버 로그인은 새 비밀번호로만 성공해야 한다.
- 기본 비밀번호 `1234`로 서버 로그인이 401로 실패할 때 WPF가 로컬 `admin / 1234` 계정으로 우회하지 않는지 확인한다.
- WPF/API로 만든 임시 비밀번호 계정이 로그인 후 메인 화면 대신 비밀번호 변경 화면을 표시하는지 확인한다.
- 비밀번호 변경 후 기존 access/refresh token이 거부되고 새 비밀번호 재로그인만 성공하는지 확인한다.

현재 role 기준:

- 사용자 관리는 WPF에서 `admin`, `system-admin`만 가능하다.
- 문서 등록과 작업순서 편집은 관리자 계열, 반장, 조장까지 허용한다.
- 보고서 작성은 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.
- `team-member`, `viewer`는 문서 열람과 FieldComment 작성 중심이다.
- FieldComment 분석·담당 지정·검토 대시보드 조회는 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`, `line-foreman`, `team-lead`에 허용한다. 선정·제외·보관 결정은 관리자 계열 역할로 더 좁게 제한한다.
- controlled copy 다운로드는 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.

서버-WPF role 정합성 기준:

- 문서 등록, 문서 버전 등록, 태그/상태 변경은 FastAPI `DOCUMENT_WRITE_ROLES`와 WPF `CanRegisterDocuments`를 같은 집합으로 유지한다.
- FieldComment 작성은 FastAPI `FIELD_COMMENT_CREATE_ROLES`와 WPF `CanWriteFieldComments` 모두 기본 role 전체를 허용한다.
- FieldComment 검토 대시보드는 FastAPI `FIELD_COMMENT_ANALYZE_ROLES`를 적용하며 `team-member`, `viewer`의 직접 조회를 거부한다.
- 접근 로그 조회와 사용자 관리는 `admin`, `system-admin`만 허용한다.
- 보고서 작성과 controlled copy 다운로드는 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.
- WPF는 서버 로그인 성공 시 서버 응답의 사용자 ID, 표시 이름, role을 현재 세션 기준으로 사용한다. 서버가 401 또는 403을 반환하면 같은 로그인 ID의 로컬 계정으로 fallback하지 않는다.
- WPF 스모크 테스트는 같은 로그인 ID의 로컬 `system-admin` 계정과 서버 `team-member` 응답을 비교해 서버 role이 버튼 권한에 우선 적용되는지 검증한다.

## 현장 최소 권한표

이 절은 구현 목록이 아니라 배포 리허설 뒤 현장 계정으로 다시 확인할 승인 기준이다. API 직접 호출, WPF UI, Android 실단말에서 같은 행을 반복하고 한 경로라도 결과가 다르면 통과로 보지 않는다.

역할은 다섯 묶음으로 나눈다.

- 시스템 운영: `system-admin`
- 일반 관리: `admin`
- 문서·보고서 관리: `document-admin`, `manager`, `assistant-manager`, `department-manager`
- 현장 감독: `line-foreman`, `team-lead`
- 현장 작업·열람: `team-member`, `viewer`

아래 표에서 `허용`은 role만 충족하면 된다는 뜻이 아니다. 활성 계정과 세션, 필요한 승인 단말, 문서 상태·버전, 채널 멤버십, 고객·현장 scope 같은 추가 조건을 모두 만족해야 한다. `조건부`는 표의 조건을 충족한 경우에만 허용하며, `금지`는 UI 버튼 숨김뿐 아니라 API 직접 호출도 거부해야 한다.

| 업무 | 시스템 운영 | 일반 관리 | 문서·보고서 관리 | 현장 감독 | 현장 작업·열람 | 추가 조건과 금지 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| WPF/API 문서 목록·상세 열람 | 허용 | 허용 | 허용 | 허용 | 허용 | 활성 인증 계정과 서버의 단일 고객·현장 scope가 일치해야 한다. 다른 scope 입력은 대상 존재와 무관하게 `404 SCOPE_NOT_FOUND`이며 감사에 남긴다. |
| Android 공개 문서 본문 열람 | 금지 | 조건부 | 조건부 | 조건부 | 조건부 | `system-admin`은 Android 본문 열람 role에서 제외한다. 나머지도 `ACTIVE` 승인 단말, 단말 바인딩 세션, 현재 공개 버전과 1회성 grant가 필요하다. |
| controlled copy 발급·저장 | 허용 | 허용 | 허용 | 금지 | 금지 | 현재 공개 버전, 사용자·세션 바인딩, 만료, 1회 사용, 크기·SHA-256 재검증을 모두 확인한다. 요청자의 업무 사유와 독립 승인은 현재 grant에 연결되지 않는다. |
| 문서·버전 등록, 태그 변경 | 허용 | 허용 | 허용 | 허용 | 금지 | 서버 `DOCUMENT_WRITE_ROLES`와 WPF 등록 버튼 집합이 같아야 한다. |
| 문서 상태·버전 상태 변경, 공개·보관·삭제 | 허용 | 허용 | 허용 | 금지 | 금지 | `DOCUMENT_GOVERNANCE_ROLES`, 변경 사유, 최신 document revision과 예상 공개 version을 적용한다. 공개·삭제는 별도 고위험 절차를 적용한다. |
| FieldComment 등록 | 허용 | 허용 | 허용 | 허용 | 허용 | 원천 내용·작성자·단말·문서/version 연결을 생성 후 바꾸거나 삭제할 수 없어야 한다. |
| FieldComment 담당 배정·정리·분석 | 허용 | 허용 | 허용 | 허용 | 금지 | `FIELD_COMMENT_ANALYZE_ROLES`, 현재 `review_revision`, 담당자, 기한, 사유를 검사한다. |
| FieldComment 검토·선정·제외·보관 결정 | 허용 | 허용 | 허용 | 금지 | 금지 | 서버는 `FIELD_COMMENT_DECIDE_ROLES`, 최신 `review_revision`, 원천 hash 불변을 확인한다. `red` 신호 또는 `conflict_flag = true`인 원천은 분석자와 같은 사용자의 `REVIEWED`·`SELECTED`·`EXCLUDED`·`ARCHIVED` 결정을 `403 INDEPENDENT_REVIEW_REQUIRED`로 거부한다. |
| 보고서 목록·근거 조회 | 허용 | 허용 | 허용 | 허용 | 허용 | 보고서의 모든 원천이 현재 적격 상태이고 호출자가 원천 연결 채널을 열람할 수 있어야 한다. 하나라도 실패하면 목록에서 보고서 전체를 제외하고 상세·source는 동일한 정제 `404`로 처리한다. 성공·거부는 감사에 남긴다. |
| 보고서 초안·확정본 작성 | 허용 | 허용 | 허용 | 금지 | 금지 | 현재 source version/revision/hash, 서로 다른 source type, report revision과 mutation receipt가 필요하다. |
| 채널 생성 | 허용 | 허용 | 허용 | 허용 | 금지 | 문서 쓰기 role만 가능하다. |
| 채널 조회·메시지·인수인계 생성 | 조건부 | 조건부 | 조건부 | 조건부 | 조건부 | `admin`, `system-admin`의 감독 범위를 제외하면 활성 채널 멤버십이 필요하다. 인수인계 수신 확인은 본인 receipt만 변경하며 다른 사용자의 receipt는 관리자 외에는 거부한다. |
| 채널 멤버 운영 | 조건부 | 조건부 | 조건부 | 조건부 | 조건부 | `admin`, `system-admin` 또는 해당 채널의 `OWNER`/`MANAGER`만 가능하다. 전역 role과 채널 내 역할을 혼동하지 않는다. |
| 작업순서 조회 | 허용 | 허용 | 허용 | 허용 | 허용 | 인증된 사용자에게만 반환한다. 현장·라인 scope가 도입된 경우 같은 조건을 추가한다. |
| 작업순서 생성·순서·상태·보류 사유 변경 | 허용 | 허용 | 허용 | 허용 | 금지 | 서버는 문서 쓰기 role, 최신 board revision과 mutation key를 검사한다. `changeReason`은 현재 선택값이므로 필수 사유를 요구하는 현장에서는 구현 공백으로 기록한다. |
| 파일 감시 운영 | 허용 | 허용 | 허용 | 금지 | 금지 | WPF 로컬 기능이며 서버 전용 권한은 아직 없다. 서버 로그인 때는 서버 role이 로컬 role보다 우선해야 한다. |
| 계정 생성·role/상태·임시 비밀번호·세션 운영 | 허용 | 조건부 | 금지 | 금지 | 금지 | `admin`은 `system-admin` 계정을 조회·생성·변경하지 못한다. 마지막 활성 `system-admin` 제거와 자기 자신 잠금·비활성화는 거부한다. |
| 승인 단말 등록·비활성화·폐기·교체 | 허용 | 허용 | 금지 | 금지 | 금지 | 상태 변경과 기존 단말 세션 폐기는 한 transaction이어야 하며 `RETIRED` 단말은 재활성화하지 않는다. |
| 접근·권한·공통 mutation 감사 조회 | 허용 | 허용 | 금지 | 금지 | 금지 | `document_access_logs`와 `/audit-events`는 `admin`, `system-admin`만 조회한다. 조회 행위 자체의 별도 감사와 내보내기 승인은 구현 보완 항목이다. |
| 외부 AI 질의·ground-truth 작성·검토 | 허용 | 허용 | 허용 | 금지 | 금지 | 외부 AI 질의는 별도 전송 승인·프롬프트·원천 권한·민감정보·kill switch를 통과해야 한다. |
| ground-truth 최종 승인·폐기 | 허용 | 허용 | 조건부 | 금지 | 금지 | 문서·보고서 관리 중 `document-admin`, `department-manager`만 허용하고 `manager`, `assistant-manager`는 금지한다. 작성·검토·1차·2차 승인자는 모두 달라야 한다. |
| AI 전송 승인·프롬프트·정책·감사·보존 운영 | 허용 | 금지 | 금지 | 금지 | 금지 | `system-admin` 전용이다. 고객·현장 scope, 최신 `stateTag`, 이중 확인과 완료 후 read-back을 적용한다. |

현장 직무명은 위 role 값과 일대일이라고 가정하지 않는다. 파일럿 시작 전에 현장 관리자, 문서관리자, 반장·조장, 작업자의 실제 직무를 role 값에 매핑하고, 겸직자는 필요한 권한의 합집합을 임의 부여하지 않고 승인된 단일 주 role과 기간이 정해진 예외 권한으로 관리한다.

## 역할·계정·단말 역검증 실행 기준

### 시험 계정과 실행 증거

- 실계정은 실제 배정된 role로 정상 허용 업무를 수행하되 고객 원문이 아닌 승인된 파일럿 자료를 사용한다. 공유 계정은 실계정으로 인정하지 않는다.
- 금지·우회 시험은 `pilot-<site>-<role>-<sequence>` 형식의 익명 시험계정을 사용한다. 증거 파일에는 익명 시험 ID를 쓰고 서버 원본 감사에는 실제 `user_id`를 유지한다.
- 역할마다 허용·금지 행을 API, WPF, Android 세 경로에 배정한다. 해당 기능이 없는 클라이언트 경로는 `N/A`와 사유를 기록하며 다른 경로의 성공으로 대체하지 않는다.
- 각 실행은 하나의 `run_id`와 요청별 `correlation_id`를 사용한다. 화면 캡처, HTTP 상태와 정제 응답, 사용자·세션·단말, 대상 문서·version/revision, 요청 사유, 감사 row ID와 서버 시각을 같은 결과 행에 연결한다.
- 허용 행은 기대한 상태 전이와 read-back까지 성공해야 한다. 금지 행은 UI 비노출·비활성화와 API 거부를 확인하고, 감사 기록 외에는 저장소·큐·알림의 업무 데이터가 바뀌지 않아야 한다.

### 계정 수명주기 시나리오

1. `admin` 또는 `system-admin` 실계정으로 각 익명 시험계정을 임시 비밀번호와 발급 사유를 넣어 만든다. 첫 로그인에서 일반 API와 refresh가 차단되고 비밀번호 변경만 허용되는지, 변경 직후 현재 세션까지 폐기되고 새 비밀번호로 다시 로그인해야만 성공하는지 확인한다.
2. 계정별 활성 세션 목록에서 session ID, 생성·만료 시각과 단말 ID를 확인한다. 세션 하나를 폐기한 결과와 전체 폐기 결과를 구분하고, 폐기 사유와 폐기자가 감사에 남는지 대조한다.
3. 계정을 `LOCKED`로 바꾼 뒤 로그인·access·refresh를 거부하고, 별도 승인으로만 `ACTIVE` 복귀시키며 비밀번호 재설정이 상태를 암묵적으로 활성화하지 않는지 확인한다.
4. 계정을 `DISABLED`로 바꾸고 서버 계정과 각 승인 PC의 로컬 계정, 채널 멤버십, 담당 FieldComment·작업순서·인수인계, 승인 단말 연결을 퇴사·업무 변경 체크리스트로 회수한다.
5. 낮은 role로 변경하기 전·중·후에 기존 세션과 직접 API 호출을 반복한다. 기존 세션이 폐기되는지, 새 로그인 전까지 기존 권한이 유지된 사례가 없는지, 새 로그인 뒤 권한표와 일치하는지 확인한다.
6. 기존 Android 단말을 비활성화하고 교체 API로 새 단말을 등록한다. 기존 단말이 `RETIRED`로 남고 재활성화되지 않으며, 기존 세션·refresh·미사용 grant와 새 단말 ID 위조가 모두 거부되는지 확인한다.

### 계정·세션·단말 동시성

다음 경계 시각은 서버 transaction의 commit 시각을 기준으로 한다. commit 이후에 시작한 요청이 하나라도 성공하거나 refresh로 새 access token을 얻으면 실패다.

1. 활성 세션으로 읽기와 쓰기를 반복하면서 관리자가 세션 하나와 전체 세션을 각각 폐기한다. 폐기 직전 요청, commit과 동시에 보낸 요청, 폐기 직후의 access·refresh·WPF 재시도·Android 재시작을 구분한다.
2. 같은 사용자의 role을 높은 권한에서 낮은 권한으로, 낮은 권한에서 높은 권한으로 바꾼다. 기존 세션은 폐기되어야 하며, 새 role은 새 로그인 뒤에만 적용되어야 한다.
3. 계정을 `LOCKED`, `DISABLED`로 바꾸는 동안 API·WPF·Android 요청을 반복한다. 잠금·비활성 commit 뒤 기존 access/refresh와 새 로그인은 모두 거부되어야 한다.
4. Android 단말을 `INACTIVE`, `RETIRED`로 바꾸고 교체 단말을 등록하는 동안 로그인·refresh·본문 grant 발급·stream을 반복한다. 기존 단말 세션 폐기와 새 단말의 별도 승인 이력을 확인한다.
5. 고위험 mutation이 권한·세션·단말 변경과 겹치면 저장 직전에 최신 권한과 state/revision을 다시 확인해야 한다. 이를 강제할 revision 또는 재검사 지점이 없는 작업은 현장 승인에서 구현 공백으로 기록한다.

권한 밖 데이터의 존재를 숨기기로 한 API는 다른 고객·현장·채널의 ID, 다른 사용자의 제한 객체와 임의 ID를 각각 호출해 모두 `404` 계약인지 확인한다. 같은 scope의 존재하는 객체에서 role이나 본인 receipt 조건만 부족한 경우는 `403` 계약을 사용한다. 정확한 계약은 [API 초안](./api.md)을 기준으로 하며, 응답 차이·길이·처리 시간으로 존재 여부가 드러나는지도 함께 확인한다.

### 고위험 작업의 공통 게이트

문서 공개·삭제와 controlled copy, FieldComment 선정·제외·보관, 보고서 확정, 계정 role/상태와 세션 폐기, 단말 비활성화·폐기·교체, AI 전송 승인·철회·kill switch·보존·legal hold는 고위험 작업으로 다룬다.

- 요청자와 승인자는 달라야 한다. 코드가 독립 승인을 강제하는 AI ground-truth는 서버 제약으로 확인하고, 그 밖의 작업은 승인번호와 승인자를 운영 기록에 먼저 남긴 뒤 실행한다. 독립 승인을 시스템 또는 상호 대조 가능한 운영 감사로 증명하지 못하면 실패다.
- 사유는 빈 값이나 관용 문구로 대신하지 않고 대상, 목적, 영향과 복구 방법을 식별할 수 있어야 한다.
- 작업 직전에 최신 문서 version/revision, FieldComment `review_revision`, 보고서 revision/source-set hash, 계정·세션·단말 상태 또는 AI `stateTag`를 읽고 mutation 조건으로 보낸다. 서버가 조건부 갱신을 지원하지 않는 작업은 동시 변경 시험 결과와 구현 공백을 기록한다.
- 성공 응답만으로 완료 처리하지 않는다. 서버 상세와 감사 로그를 다시 읽어 기대 state, actor, 승인자·승인번호, 사유, revision/hash와 mutation receipt가 일치해야 한다.

현재 controlled copy API 감사 사유는 서버가 정한 고정 문구이며 요청자의 업무 사유를 입력받지 않는다. 독립 승인과 업무 사유를 grant에 연결해야 하는 현장에서는 이 구현을 통과로 볼 수 없으며 구현 보완 항목으로 기록한다.

### 완료 판정

- 역할별 허용 시나리오 성공률은 `100%`, 금지 시나리오의 UI·API·로컬 fallback·직접 URL 우회는 `0건`이어야 한다.
- 비활성 계정, 폐기 세션, `INACTIVE`·`RETIRED`·분실 단말의 commit 뒤 API·WPF·Android 재접속은 `0건`이어야 한다.
- 서버 URL이 설정된 상태의 `401`·`403`·연결 불가·timeout·TLS 오류 뒤 로컬 fallback은 `0건`이어야 한다. 서버 URL 미설정 로컬 운영은 별도 감사가 있는 경우에만 성공으로 센다.
- 고위험 작업의 독립 승인·사유·최신 state/revision·완료 read-back 누락과 허용·거부 감사 누락은 각각 `0건`이어야 한다.
- 위 기준을 만족하지 못한 행은 권한 우회가 실제 발생하지 않았더라도 `FAIL`로 두고, 수정과 새 `run_id` 재검증 전에는 파일럿 운영 승인을 내리지 않는다.

## 로컬 계정과 서버 계정의 통합 운영 절차

서버 계정이 정상 운영 경로이고 WPF 로컬 계정은 서버 미설정 설치 또는 사전 승인된 비상 운영 경로다. 같은 로그인 ID를 두 저장소에 만들 수 있지만 동일 계정으로 간주하거나 자동 병합하지 않는다.

| 상태 | 로그인·fallback 판정 | 허용 범위 | 필수 조치와 감사 |
| --- | --- | --- | --- |
| 서버 URL 미설정 | 승인된 로컬 계정 로그인 허용 | 해당 PC에 사전 승인된 로컬 업무 | `local_fallback_no_server_config` 사유, 사용자·PC·시각·승인번호를 로컬 감사에 남긴다. |
| DNS/TCP 실패, 연결 거부, timeout | 자동 fallback 금지 | 없음. 로컬 데이터와 보존 큐는 유지 | 네트워크·방화벽·현재 서버 주소를 확인한다. 감사 가능한 비상 fallback UI가 구현되기 전에는 로컬 로그인으로 전환하지 않는다. |
| 서버 로그인 성공 | 서버 계정만 사용 | 서버 role과 scope가 허용한 업무 | 같은 ID의 로컬 role을 버튼·작성자·동기화 권한에 사용하지 않는다. |
| 서버 `401` | fallback 금지 | 없음 | 자격증명 또는 세션 문제로 안내하고 재로그인한다. 로컬 데이터와 기존 큐는 보존한다. |
| 서버 `403` | fallback 금지 | 없음 | 계정·role·단말 상태를 관리자에게 확인한다. 로컬 데이터와 기존 큐는 보존한다. |
| 서버 `404`, `409`, `422`, `429`, `5xx` | fallback 금지 | 없음 | 요청·상태·한도·서버 장애를 각각 조치하며 인증 저장소를 바꾸지 않는다. |
| TLS 인증서·호스트명·신뢰·폐기 확인 실패, 응답 위변조 의심 | fallback 금지 | 없음 | 보안 사고 후보로 중단하고 인증서와 서버 주소를 확인한다. 일반 연결 불가로 축소하지 않는다. |

현재 WPF는 서버 URL이 없을 때만 로컬 로그인을 시도한다. HTTPS `HttpClientHandler`는 인증서 폐기 목록 확인을 켜며, 인증서·chain·호스트명·유효기간·폐기 확인에 실패한 연결을 우회하지 않는다. 서버 URL이 설정된 상태의 `HttpRequestException`·timeout도 로컬 로그인으로 자동 우회하지 않고, 인증서 오류는 PC 시간·운영 서버 이름·폐기 상태·CRL/OCSP 접근·사내 인증서 신뢰 배포를, 일반 연결 오류는 네트워크·방화벽·현재 서버 주소를 확인하도록 안내한다. 실패 화면에는 실패 내용, 보존한 로컬 원천·`Files`·동기화 큐·알림 cursor·처리 `message_id`, 처리 담당자와 가능한 다음 행동을 함께 표시한다. 로컬 저장소 시작 실패도 자동 초기화나 재설치를 먼저 실행하지 않고 DB와 `Files`의 동시 보존과 관리자 승인을 요구한다. 사전 승인된 비상 fallback은 사용자·PC·서버 scope·사유·승인번호를 감사하는 별도 UI가 구현되기 전까지 자동 허용하지 않는다.

복구 안내는 보안 통제의 일부이므로 마우스 사용을 전제로 하지 않는다. 로그인 화면은 키보드 초점이 가능한 읽기 전용 스크롤 영역, `Alt+R` 다시 시도와 `Alt+X` 종료 접근 키, 크기 조절 창과 줄바꿈 버튼 배치를 사용한다. 실제 운영 승인은 처음 화면을 본 참여자가 추가 설명 없이 담당자와 다음 행동을 식별하고, 긴 오류의 끝까지 접근하며, 200% 이상 배율에서 버튼 겹침 0건을 확인한 `windows-startup-ux.csv`와 화면 증거가 있어야 한다.

운영 전환과 비상 사용은 다음 순서로 처리한다.

1. 현장 책임자가 서버 사용 여부, 비상 로컬 사용 PC·사용자·허용 업무·승인 유효기간을 승인한다.
2. 계정 운영자는 서버 계정을 발급하고 임시 비밀번호 변경을 확인한다. 로컬 계정이 꼭 필요한 승인 PC에만 별도로 발급하며 기본 관리자 비밀번호를 사용하지 않는다.
3. 서버 전환일에는 로컬 세션을 종료하고 서버 계정으로 재로그인한 뒤 서버 사용자 ID와 role을 화면·버튼·감사에서 확인한다. 로컬 계정은 비상 승인이 없으면 `DISABLED`로 전환한다.
4. 비상 fallback 때는 원인, 시작 시각, 승인자, 사용 PC와 허용 업무를 기록한다. 서버 권한이 필요한 controlled copy, 계정·단말, AI 운영은 수행하지 않는다.
5. 연결 복구 뒤 로컬 원천과 큐를 삭제하지 않고 서버 revision·hash와 대조해 동기화한다. `401`·`403` 항목은 자동 재시도하지 않고 새 서버 로그인과 권한 확인 뒤 재개한다.
6. 비상 종료 시각, 동기화 결과, 충돌·보류 건, 로컬 계정 재비활성화와 감사 대조 결과를 같은 `run_id`로 닫는다.

## 계정 수명주기 SLA

아래 시간은 사건 접수 또는 승인 효력 시각부터 잰 파일럿 기본 상한이다. 고객 정책이 더 엄격하면 그 값을 적용하고, 완화하려면 보안 책임자의 서면 승인이 필요하다.

| 사건 | 처리 상한 | 완료 증거 |
| --- | --- | --- |
| 신규·변경 계정 | 첫 근무 시작 전 | 승인된 role, 8자 이상 임시 비밀번호, `must_change_password = true`, 최초 변경 뒤 구 세션 폐기와 새 비밀번호로 재로그인 |
| 미변경 임시 비밀번호 | 발급 후 24시간 | 미변경 계정 `LOCKED`, 전달 원문 미보존, 재발급 승인과 사유 |
| 비밀번호 노출 의심·계정 오용 | 접수 후 15분 | `LOCKED`, 전체 세션 `REVOKED`, 사고번호, 새 비밀번호와 재활성화의 별도 승인 |
| 퇴사·계약 종료 | 효력 시각 전 | 서버 계정 `DISABLED`, 모든 로컬 계정 비활성, 전체 세션 폐기, 승인 단말·채널·인수인계·담당 업무 회수 |
| 업무·role 변경 | 변경된 업무 시작 전 | 기존 세션 폐기, 최소 role 재부여, 채널·문서·AI scope 재검토, 새 로그인 권한표 확인 |
| 불필요·의심 세션 | 확인 후 15분 | 대상 또는 전체 세션 폐기, access·refresh 재사용 0건 |
| 분실·도난 단말 | 접수 후 15분 | 단말 `INACTIVE`, 해당 세션 폐기, 마지막 접속과 사고 `run_id`, MDM 원격 잠금·초기화 요청 |
| 단말 교체 | 새 단말 업무 사용 전 | 기존 단말 `RETIRED`, 새 단말 별도 등록·승인, 기존 token·grant 재사용 0건, 교체 연결 이력 |
| 장기 미사용 계정 | 30일 도달 당일 | 사용 필요 재승인이 없으면 `LOCKED`; 90일에는 `DISABLED` 검토 |

현재 서버는 임시 비밀번호의 24시간 자동 만료와 30일 장기 미사용 자동 잠금을 구현하지 않았다. 현장 운영자가 기한 보고서로 수동 통제하거나 구현을 보완해야 하며, 어느 쪽도 입증하지 못하면 해당 SLA는 미충족이다.

서버 role·상태·비밀번호 변경은 기존 서버 세션을 폐기하지만 WPF 로컬 계정을 자동 변경하지 않는다. 퇴사·업무 변경 체크리스트에는 사용자가 로컬 계정을 가진 모든 PC를 반드시 포함하며, 목록을 확인할 수 없으면 회수 완료로 판정하지 않는다.

## 감사 책임·보존·정기 검토

권한 검증의 성공·거부·실패는 모두 감사 대상이다. 최소 필드는 `run_id`/`correlation_id`, 결과와 HTTP 상태, 사용자·role, 세션, 단말 또는 WPF PC 식별자, 고객·현장 scope, 대상 종류·ID, 문서 version과 domain revision, 요청 사유, 승인자·승인번호, 전후 상태, 서버 시각이다. 비밀번호, access/refresh token, controlled copy/grant 원문, 고객 문서 본문과 AI 질의·응답 원문은 감사에 넣지 않는다.

`audit_event_envelopes`와 `sync_mutation_receipts`는 operation key가 있는 문서 권위 변경, FieldComment 검토, 보고서 상태 전이, 작업순서 변경부터 적용한다. 공통 envelope는 actor/role/session, 선택 device, target/version/revision, 사유·승인, 전후 hash, 성공·거부·충돌 결과, HTTP status, server time, 선택 run ID와 필수 correlation ID를 같은 형식으로 보존한다. 보고서 `REVIEWED`는 승인 대기와 빈 승인자, `APPROVED`·`ARCHIVED`는 승인 완료와 전이 actor를 기록하고 별도 승인 모델이 없는 행위는 `NOT_REQUIRED`로 표시해 승인을 받은 것처럼 추정하지 않는다.

기존 `activity_history`와 도메인 감사는 삭제·수정·백필하지 않는다. `/audit-events`는 공통 envelope가 없는 행을 `이전 형식·일부 필드 없음`으로 표시하고 누락값을 `null`로 반환한다. 공통 적용 대상이 아닌 API는 여전히 모든 공통 필드를 보존한다고 가정할 수 없으므로, 세 경로 대조에서 필수 필드가 빠진 행은 화면 결과가 맞더라도 감사 누락으로 실패 처리한다.

공통 감사의 `safe_payload_json`과 실패 response snapshot에는 정제 code, 대상 식별자·revision, operation/receipt 연결만 허용한다. access/refresh token, 비밀번호, controlled copy/grant 원문, 고객 문서·FieldComment·보고서 본문, 로컬 절대경로, 개인 이름·IP 같은 불필요한 개인정보는 넣지 않는다. 사유에 비밀 키 이름이나 로컬 절대경로가 섞이면 저장 전에 `[REDACTED]`, `[LOCAL_PATH_REDACTED]`로 치환한다. 전후 업무 상태는 원문 대신 SHA-256으로 기록한다.

- 계정 운영자는 계정·세션·단말 변경과 SLA 준수 증거를 남긴다.
- 문서 책임자는 문서 공개, controlled copy, FieldComment 결정, 보고서와 작업순서의 version/revision·사유를 확인한다.
- 시스템 운영자는 서버 `activity_history`, `document_access_logs`, AI 운영 감사와 WPF 로컬 감사를 수집하고 시각 동기화·무결성·백업·조회 권한을 관리한다.
- 현장 보안 책임자는 거부·우회 시도, 404/403 계약, 감사 누락과 정기 권한 재인증을 검토한다. 자기 작업을 최종 승인하거나 자기 감사 내보내기만으로 종결하지 않는다.

파일럿 기본 보존 기간은 접근·권한·계정·세션·단말·고위험 작업 감사와 내보낸 검증 증거 모두 최소 1년이다. 고객 계약, 법률, 사고 조사나 legal hold가 더 긴 보존을 요구하면 그 기간을 우선한다. 현재 일반 감사 자동 purge 정책이 확정되지 않았으므로 기간 만료만으로 DB row나 로컬 테스트 증거를 삭제하지 않고, 승인된 보존 정책과 복구 가능한 백업을 확인한 뒤 별도 폐기 절차로 처리한다.

정기 검토 주기는 다음을 기본으로 한다.

- 파일럿 중 매일: 전날의 고위험 작업, `401`·`403`, fallback, 단말 상태 변경과 감사 누락
- 매주: 역할별 허용·금지 표본, 폐기 세션·비활성 계정·분실 단말 재접속, `run_id`/`correlation_id` 대조
- 매월: 전체 활성 계정·role·채널 멤버십·로컬 계정 PC·승인 단말·장기 미사용·감사 조회자 재인증
- 분기마다: 현장 책임자와 문서·보안 책임자의 전체 최소 권한 재승인과 controlled copy·AI 운영 권한 재검토
- 매년 및 보존 정책 변경 때: 감사 백업 복원, hash·row 수·시간 순서, legal hold와 폐기 절차 리허설

## 역할별 오류 문구 사용성 기준

권한 실패 화면은 한글로 원인 범주, 사용자가 취할 다음 조치, 관리자 문의 필요 여부, 입력 파일·로컬 원천·동기화 큐의 보존 상태를 알려야 한다. 서버 영문 `detail`, 예외 stack, 내부 경로와 token을 그대로 표시하지 않는다. `404` 존재 은닉 계약이 필요한 화면은 숨긴 대상의 종류나 존재를 문구로 확인해 주지 않는다.

| HTTP/공개 오류 코드 | 사용자 안내 범주 | 다음 조치 |
| --- | --- | --- |
| `401` | 로그인 만료·인증 필요 | 다시 로그인한다. `DEVICE_NOT_APPROVED`이면 단말 승인 상태를 관리자에게 확인한다. |
| `403 PERMISSION_DENIED` | 권한 없음 | 계정 role과 활성 상태를 관리자에게 확인한다. |
| `403/401 DEVICE_NOT_APPROVED` | 단말 비승인 | 재설치·초기화하지 않고 등록·활성·교체 상태를 확인한다. |
| `404 SCOPE_NOT_FOUND` | 다른 고객·현장 범위 | 서버 주소와 현장 설정을 확인한다. 대상 ID나 실제 존재 여부는 표시하지 않는다. |
| `404 SOURCE_NOT_VISIBLE` 또는 `RESOURCE_NOT_FOUND` | 원천 없음·비공개 | 목록을 새로 조회하고 필요하면 공개 상태를 관리자에게 확인한다. 존재 여부는 확정해 말하지 않는다. |

## 단일 고객·현장 운영 경계

파일럿의 서버 PC 1대는 고객 하나와 현장 하나만 담당한다. 서버 경계값은 `FLOWNOTE_CUSTOMER_SCOPE`, `FLOWNOTE_SITE_SCOPE`이며 설정하지 않으면 기존 AI scope 설정을 사용한다. 보호 API는 `X-FlowNote-Customer-Scope`, `X-FlowNote-Site-Scope`가 생략되면 현재 서버 경계로 해석하고, 값이 들어오면 정확히 일치하는 경우만 허용한다. 로그인·refresh의 선택 `customerScope`, `siteScope`도 같은 규칙을 적용하며 헤더와 본문 값이 다르면 거부한다.

이 결정에서는 계정·문서·채널·보고서·검색 후보에 고객·현장 열을 추가하지 않는다. 기존 SQLite와 `storage/`는 이미 이 서버 경계 안의 데이터이므로 행 이동, ID 변경, 파일 재배치가 없다. 전환 전후 핵심 테이블 row 수와 파일 SHA-256을 비교하고, rollback은 이전 서버 패키지와 기존 설정으로 되돌린 뒤 같은 DB·파일을 그대로 연다. 새 설정을 제거해도 업무 행 형식은 바뀌지 않는다. 여러 고객 또는 여러 현장을 한 서버에서 운영하려면 별도 결정, 전 엔티티 scope 외래키, 인덱스, 백필·검증·rollback 도구와 교차 scope 부정 테스트가 먼저 필요하다.

실계정 사용자와 익명 시험계정 사용자를 역할 묶음별로 포함해 추가 설명 없이 문구를 읽고 다음 조치를 선택하게 한다. 현장이 별도 승인값을 정하지 않았다면 다음 파일럿 기본 임계값을 사용한다.

- 한글 문구와 원인 범주 표시율 `100%`
- 추가 설명 없이 의미를 이해하고 올바른 다음 조치를 고른 비율 `90% 이상`
- 일반 권한 실패의 올바른 조치 선택 중앙값 `60초 이하`, 계정·단말·보안 관리자 문의가 필요한 실패 `120초 이하`
- 로컬 데이터나 동기화 큐가 남는 오류에서 보존 상태를 올바르게 답한 비율 `100%`
- 권한 밖 데이터의 존재를 유추할 수 있는 문구, 영문 서버 원문, 비밀값·내부 경로 노출 `0건`

역할, 오류 코드, 문구, 선택한 조치, 이해 여부, 처리 시간, 도움 요청과 관찰자 메모를 같은 실행 결과에 남긴다. 표본 수와 현장 승인 임계값은 실행 전에 고정하며 결과를 본 뒤 낮추지 않는다.

## 서버 인증

FastAPI 서버는 HMAC 서명 Bearer access token과 `auth_sessions` 테이블을 함께 사용한다.

- 로그인은 `auth_sessions` row를 만들고 access token과 refresh token을 반환한다.
- refresh는 같은 세션에서 `access_token_id`와 `refresh_token_hash`를 교체한다.
- refresh 후 이전 access token과 이전 refresh token은 거부된다.
- logout은 세션을 `REVOKED`로 변경한다.
- 보호 API는 세션 상태, 폐기 시각, access token ID, 만료 시각과 세션에 묶인 단말의 현재 `ACTIVE` 상태를 모두 검증한다. refresh도 계정과 단말 활성 상태를 다시 확인한다.
- 인증 없이 사용할 수 있는 경로는 루트 `/`, 세 상태 확인 API, `GET /api/v1/sync/manifest`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/tags`다. 태그 생성과 그 밖의 보호 API는 각 경로에 맞는 인증과 role을 요구한다.
- WPF는 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정 로그인으로 우회하지 않는다.
- 서버 URL이 없는 승인된 로컬 운영 PC에서만 WPF 로컬 계정 로그인을 사용한다.

운영 전에는 `FLOWNOTE_ACCESS_TOKEN_SECRET`을 현장별 비밀값으로 바꾸고 Git에 저장하지 않는다. 서버 운영 DB와 서버 `storage\`는 같은 서버 PC의 로컬 디스크에 두되, 서버 실행 계정과 운영 관리자만 접근할 수 있게 NTFS 권한을 제한한다. 계정 발급, 비밀번호 재설정, 비활성화 절차는 [배포 문서의 운영 계정 발급과 변경 절차](./deployment.md#운영-계정-발급과-변경-절차)를 따른다.

## 문서 열람 보호

WPF 문서 뷰어는 로컬 앱 계층에서 보호한다.

- Windows 문서 뷰어는 시간 기반 자동 닫힘을 수행하지 않고 사용자가 직접 닫을 때까지 유지한다.
- 닫힘 사유는 신규 열람에서 `window_closed`, 다운로드 차단 시 `download_blocked`로 기록한다. 기존 `auto_closed` 값은 과거 감사·동기화 호환을 위해 보존한다.
- PDF는 WebView2 기반 표시를 우선하고 저장/다운로드 이벤트를 차단한다.
- 텍스트, 이미지, Excel은 앱 내부 읽기 전용 미리보기로 표시한다.
- TXT/PDF/XLSX/이미지의 정상, 비정상, 한글 파일명, 큰 파일 기준과 CAD/HWP 제외 범위는 [문서 미리보기 안정화 기준](../apps/windows/docs/document-preview-stability.md)을 따른다.

허용 role의 controlled copy도 로컬 원본을 직접 복사하지 않는다. WPF는 서버에 현재 문서/버전의 티켓을 요청하고 같은 Bearer 사용자·로그인 세션으로 한 번만 스트리밍한다. 서버는 공개 상태와 정확한 공개 버전, 저장소 경계, 파일 크기, 등록 SHA-256을 발급 전과 전송 전에 검사한다. 티켓 원문은 DB에 저장하지 않고 SHA-256만 보존하며 기본 60초 후 만료된다. Range 요청, 다른 사용자·세션, 재사용과 만료 후 요청은 거부되고 성공·실패·차단을 모두 감사한다. 응답은 서버 로컬 경로나 `storage_key`를 노출하지 않는다.

Android 본문 열람은 WPF controlled copy와 별도 계약이다. 앱은 승인 단말과 현장 열람 role에 묶인 기본 60초 1회성 grant로 `inline` 스트림만 받고 외부 앱 열기, 공유 Intent, `FileProvider`, 공개 저장소 쓰기를 제공하지 않는다. 서버는 발급과 스트림 때 사용자·세션·단말·공개 버전·크기·SHA-256을 재검사하고 성공·실패·만료를 문서 버전 단위로 감사한다. 응답과 앱 임시 파일명은 원본 파일명을 사용하지 않는다.

수신 파일은 `cacheDir/secure-document-viewer/`의 앱 전용 내부 디렉터리에 확장자 없는 난수 이름으로만 잠시 둔다. 수신 길이, 응답/계약 SHA-256이 모두 일치한 뒤에만 `PdfRenderer`, `BitmapFactory`, 읽기 전용 TextView로 표시한다. 손상·과대·네트워크 오류에는 부분 파일을 즉시 제거한다. 뷰어 종료, 백그라운드 전환, 자동 닫힘, 오류, 로그아웃에서 삭제하고 다음 앱 시작 시 남은 파일을 다시 정리한다. 뷰어 Activity는 exported가 아니고 최근 항목에서 제외하며 `FLAG_SECURE`로 일반 화면 캡처와 미러링을 차단한다. 이 제어는 루팅·변조 단말이나 외부 카메라 촬영까지 막는 DRM 보장이 아니므로 승인 단말·MDM 정책을 함께 적용한다.

## 운영 데이터 보호

운영 기준 경로와 백업 대상은 [배포 문서](./deployment.md)를 따른다.

- 서버 SQLite, 서버 `storage\`, WPF 로컬 SQLite, WPF `Files\`는 운영 데이터이다.
- 운영 `.env`, 서비스 환경 변수, token secret, 비밀번호, 고객 문서는 Git에 올리지 않는다.
- 서버 PC 방화벽은 승인된 Windows WPF 클라이언트와 Android 현장 단말이 접근할 FastAPI 포트만 허용한다.
- 일반 브라우저 직접 접근은 초기 운영 기준이 아니며 승인된 설치형 클라이언트 접근을 기본으로 한다.
- Windows와 Android 채널 알림은 업무 채널, 서버 사용자, role, 클라이언트/단말 승인 상태를 기준으로 표시한다. 개인 메신저 대화 수집, 개인 휴대폰 기본 배포, GPS/근태 추적은 포함하지 않는다.
- 채널·인수인계 알림은 외부 인터넷에 의존하지 않는 사내망 HTTPS polling이다. Android는 로그인 동안 15초 `specialUse` foreground service를 사용하고 서버 주소+사용자 scope별 cursor를 항목 표시 직후 보존한다. WPF는 credential을 제외해 정규화한 서버 scope와 사용자 ID별 cursor·처리 `message_id`를 로컬 SQLite에 격리한다.
- WPF의 인증서 갱신·폐기와 서버 주소 변경 리허설은 기존 세션 요청 차단, 로컬 로그인 자동 우회 차단, 동기화 큐와 알림 polling 중지, 로컬 원천·큐·cursor 보존을 각각 확인한다. 인증서 신뢰 또는 서버 재결합을 승인하기 전에는 전송을 재개하지 않으며 복구 후 중복 전송은 0건이어야 한다. 결과는 같은 `run_id`의 `scenario-results/windows-network-fail-closed.csv`와 화면·WPF 로그·서버 감사 증거에 연결한다.
- Android access/refresh token과 FieldComment·사진·인수인계 outbox JSON은 Android Keystore 비반출 AES-256 GCM 키로 암호화한다. 새 outbox 사진은 선택 즉시 앱 전용 내부 저장소의 AES-GCM 파일로 복사하고 마지막으로 확인한 활성 채널·수신자 목록도 서버 URL+사용자 범위별 암호문으로 보존한다. backup은 금지하고 DB 상태·cursor 같은 비본문 메타데이터만 평문으로 둔다. 암호문 손상·키 무효화로 복호화할 수 없으면 재전송 작업을 crash로 끝내지 않고, 재설치·초기화를 금지하고 관리자에게 단말 교체 점검을 요청하는 한글 안내를 표시한다.
- Android 화면은 전송 완료·대기·실패를 색상만으로 구분하지 않고 서로 다른 아이콘과 한글 상태명·건수를 함께 표시한다. 수동 `실패 항목 다시 보내기`는 로그인 상태의 `FAILED` row만 기존 멱등키로 전송하며, 신규 `PENDING`과 완료된 `SYNCED` row는 선택하지 않는다. 자동 전송만 재시도 시점에 맞춰 `PENDING`과 `FAILED`를 처리한다.
- 정상 연결 표시 목표는 30초, 5분 이상 단절 복구 목표는 연결 회복 후 30초+page 전송 시간이다. `message_id` 고정 시스템 알림으로 crash 경계 시각 중복을 최대 1건으로 제한하고 서버 읽음/receipt 중복 row는 0건을 요구한다.
- 재부팅은 저장 세션이 있으면 서비스를 재개하고 access 401은 refresh를 한 번 회전한다. refresh 거부는 token 폐기와 서비스 중단이다. Android 강제 중지는 OS가 자동 복구를 차단하므로 MDM kiosk 재실행 또는 사용자 재실행을 운영 통제로 둔다.
- 제한 주기 WorkManager는 Doze 지연 때문에 목표 전달 수단으로 사용하지 않는다. 사내 relay push는 MDM 허용, 상호 인증, 감사, 배터리 실기 검증 후의 선택지이며 FCM 같은 외부 클라우드 의존은 기본 범위에 없다. relay를 추가해도 cursor polling은 missed notification 복구 원천이다.
- 백업 저장소에도 운영 DB, 고객 문서, 비밀값이 포함되므로 접근 권한을 운영 관리자에게 제한한다.

## 외부 AI 전송과 운영자 승인

외부 AI 호출은 기본 비활성화하며 서버 설치나 provider 자격증명 등록만으로 켜지지 않는다. `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`가 기본이고, 이 값을 켜더라도 고객·현장·provider·model·목적·source type이 일치하는 미만료·미철회 승인, 승인·활성 프롬프트, 전역/현장 kill switch와 운영 한도를 모두 통과해야 한다. 승인·프롬프트·정책·감사·보존 API와 WPF `AI 운영` 화면은 `system-admin`만 사용한다.

WPF `AI 정답셋`의 `운영 준비도` 탭은 외부 호출 차단 사유를 숨기지 않는다. 고객 승인 `ANONYMOUS_FIELD` 사례와 합성 `SMOKE_REGRESSION`을 분리하고, 부족한 원천·24칸 범주/유형, 네 dataset 역할 분리, 최신 평가 run, 독립 표본 검토, provider 심사, 기능 플래그와 어댑터 상태를 함께 표시한다. 각 미충족 항목에는 현장 데이터·평가·정보보호·법무·고객·시스템 운영 중 담당 역할과 다음 조치를 붙인다. 화면에 자격증명, endpoint, 고객 원문이나 로컬 경로는 표시하지 않는다.

WPF `AI 운영 > 민감정보 정책`은 현재 고객·현장이라는 적용 범위만 표시하고 실제 scope 식별값은 표시하지 않는다. 정책은 작성자·검토자·승인자가 서로 다른 `system-admin`이어야 활성화할 수 있다. 상태 변경은 이중 확인, 최신 `stateTag`, 안정 operation key와 완료 뒤 read-back을 사용한다. 정책 원문·고객 식별자는 작성 요청에만 포함되며 목록·상세·감사·CSV에는 content hash와 항목 수로 대체한다. provider endpoint와 자격정보는 이 화면이나 응답에 포함하지 않는다.

- 고객의 서면 외부 전송 허용 범위, 허용 현장과 원천 유형, 승인 만료일
- provider와 model, 전송·처리 지역, 암호화, 보존 기간, 재위탁자, 입력/출력의 학습 사용 금지와 삭제 조건
- 승인된 프롬프트 버전, 응답 저장 방식, 사고 대응 연락처와 승인 철회 절차
- 시험 질의의 근거 인용 검증과 고객 담당자 확인

FlowNote의 `PUBLISHED`는 현장 사용자에게 공개되었다는 뜻이지 외부 사업자 전송 승인이 아니다. 고객 문서와 그 일부, FieldComment, 사진/OCR, 작업순서 이력, 보고서 근거는 고객 승인 없이는 모두 외부 전송 금지다. 승인 후에도 비밀번호·API key·token·인증서/개인키, 주민등록번호·금융/건강정보 등 고유·민감 개인정보, 고객이 대외비/수출통제/영업비밀로 지정한 내용, 얼굴·차량번호 등 불필요한 식별정보, `EXCLUDED`/`ARCHIVED` FieldComment, 삭제·비공개 문서와 승인 범위 밖 현장 데이터는 전송하지 않는다.

질의 생성 코드는 query snapshot 시점에 고객·현장 승인, source type, 원천 상태, 작성자 계정 상태·role과 연결 채널 멤버십을 다시 검사한다. 외부 전송 대상 FieldComment는 `ANALYZED`, `REVIEWED`, `SELECTED`로 제한하고, 문서는 삭제되지 않은 현재 공개 버전, 작업순서는 존재하는 변경 이력, 보고서는 비보관 보고서와 유효한 실제 source만 적격으로 선택한다. provider/model/system prompt는 서버 설정과 승인 프롬프트에서 선택하므로 사용자가 임의로 바꿀 수 없다.

provider 경계는 필터를 통과한 질의와 제한 길이의 최소 발췌, candidate/source/version/trace ID, content hash, rank, prompt version, 고정 출력 형식만 받는다. 전체 파일·사진·첨부, 사용자명, 로컬 경로, 내부 URL과 제외 원천은 전달하지 않는다. 사용자 질의의 주민등록번호·전화번호·이메일은 대체 표식으로 마스킹한다. 원천의 주민등록번호·전화번호·이메일, 계정·비밀번호·API key·token·로컬 경로·고객 식별자, prompt injection 지시와 `ai_sensitive_data_policies`의 현장별 금칙어는 검색 후보 생성 단계에서 원천 전체를 제외한다. 차단 원문은 후보, 일반 로그와 근거 snapshot에 남기지 않는다.

활성 민감정보 정책은 정책 ID·content hash·revision으로 snapshot한다. kill switch는 민감정보 정책보다 먼저 평가한다. 이어서 정책 승인 철회·폐기와 snapshot 변경을 provider 직전에 다시 확인해 호출을 막는다. provider 실행 중 정책이 바뀌면 응답을 저장·노출하지 않고 폐기한다. 정책이 한 번도 운영된 적 없는 기존 scope는 기본 정적 필터를 유지하지만, 활성 정책의 승인 철회나 폐기 뒤에는 새 승인 버전이 활성화될 때까지 `AI_SENSITIVE_POLICY_NOT_ACTIVE`로 차단한다.

provider 응답은 크기 제한 안의 완전한 JSON이어야 하며 claim마다 중복 없는 기존 candidate ID가 필요하다. 서버는 숫자, 핵심 토큰 겹침, 부정 극성을 규칙으로 대조하고 summary도 인용된 근거 전체와 다시 확인한다. 모델 자기평가만으로 의미 일치를 승인하지 않는다. 낮은 확신은 `humanReviewRequired` 정상 보류, 명백한 모순·인용 오류·prompt injection은 본문 전체 폐기다. provider 응답 뒤에는 승인, kill switch/한도, 원천 상태·hash, 사용자 열람 권한을 재조회하며 바뀐 결과는 저장하거나 노출하지 않는다.

질의와 저장이 승인된 응답 본문은 제한 데이터로 취급한다. 생성·조회 API는 보고서 작성 role만 사용하며, 조회 API는 질의·응답 본문·citation 목록을 반환하지 않고 질의 상태·응답 hash·적격/제외 근거 snapshot만 반환한다. `system-admin` 질의 감사와 보존 상세도 서버 설정의 현재 고객·현장 scope로 고정한다. WPF 질의 목록은 `externalTransferOccurred`를 차단 코드와 별도로 표시하고, `외부 호출 비활성`, `준비도 미달`, `정책 차단`, `kill switch`마다 담당자와 다음 행동을 보여준다. WPF 메뉴는 서버 role이 `system-admin`일 때만 보이고 서버 API도 같은 권한을 재검사한다. 단일 만료·hold 설정·hold 해제 API는 다른 scope의 query/hold ID 존재 여부를 드러내지 않고 `404`로 처리한다. 일반 서버/프록시 로그에는 질의, 프롬프트, 근거 본문, 응답, 자격증명, 검출한 금칙 원문이나 provider raw 오류를 남기지 않는다.

질의 원문과 저장 승인 응답은 기본 90일이며 `DO_NOT_STORE`는 응답 hash만 남긴다. 서버 lifespan의 만료 스케줄러는 기본 1시간 간격으로 질의 payload를 `[EXPIRED]`로 비식별화하고 응답 원문을 삭제한다. `system-admin`은 만료분 전체 처리를 즉시 실행하거나 현재 scope의 단일 질의를 즉시 만료할 수 있다. 두 경로 모두 query/response hash, 근거·인용·호출 메타데이터와 외래키를 보존하고 처리 건마다 `ai_retention_audits`에 삭제·비식별화 동작을 남긴다.

법무·감사 보존 명령은 `ai_query_legal_holds`의 근거 번호, 사유, 설정자와 시각으로 등록한다. 활성 hold가 있는 질의는 정기·수동 일괄·단일 즉시 만료에서 모두 제외한다. 해제는 원래 row를 삭제하지 않고 해제자·시각·사유를 기록한 뒤부터 만료 처리를 허용한다. WPF 고위험 조작은 사유/근거 번호 입력, 이중 확인, 최신 `stateTag` 검사를 거치며 조작별 operation key를 응답 유실 재시도에도 유지한다. 성공 뒤 서버 상세를 다시 읽어 query 상태, hold 원본 row와 감사 event가 모두 확인된 경우에만 완료로 표시한다. hold에는 원문을 복제하지 않으며 장기 archive는 원문이 아닌 query/response hash, source/version/trace ID, 승인·프롬프트·호출·인용·보존 감사 metadata를 기준으로 한다.

승인 만료, 고객 요청, provider 조건 변경, 정보 유출 의심이 발생하면 운영자는 기능 플래그를 끄고 승인을 철회해 신규 호출을 즉시 차단한다. 기존 원천과 `ai_search_candidates`는 삭제하지 않으며 외부 호출 없는 후보 재생성·목록·품질 점검은 계속 동작한다. 사고 분석에는 정제된 감사 로그를 사용하고 provider에 보낸 원문을 일반 로그에서 복구하려 하지 않는다.

실제 provider 네트워크 연동은 계약, 처리·저장·백업 지역, 법적·고객 승인, 보존과 삭제, 비용 한도, 장애 격리와 사람의 최종 판단 책임이 모두 승인된 뒤 별도 구현·활성화한다. `FAKE`와 명시적 test scope의 `NETWORK_TEST` 결과, 합성 48건 통과는 이 승인을 대신하지 않는다. 그 전에는 `provider_start_ready=false` 또는 외부 호출 기능/어댑터 비활성 상태를 유지한다.

### Provider 운영 착수 심사

운영 provider client를 구현하거나 활성화하기 전에 provider/model별로 다음 항목을 문서 근거와 함께 심사한다. 확인되지 않은 값은 추정 승인하지 않고 `PENDING`, 허용할 수 없는 조건은 `FAIL` 또는 해당 영역 `REJECTED`로 기록한다.

| 항목 | 통과 기준 |
| --- | --- |
| 계약 조건 | 허용 목적, 금지 목적, 책임 범위, 재위탁자와 변경 통지 조건이 확인됨 |
| 데이터 보존 | 입력·출력·로그의 위치와 기간, 삭제 요청·계약 종료 후 삭제 절차가 확인됨 |
| 학습 사용 | 고객 입력·출력·metadata의 모델 학습/개선 사용 여부가 계약으로 확인되고 필요한 opt-out이 적용됨 |
| 전송/처리 지역 | 저장·처리·백업 지역과 국외 이전 근거가 고객·법무 허용 범위와 일치함 |
| TLS | HTTPS/TLS 최소 버전, 인증서 검증, 비밀 저장·회전 방법이 확인됨 |
| timeout | 연결·응답 timeout이 FlowNote 운영 정책 안에 있고 무한 대기가 없음 |
| 429 | `Retry-After` 또는 제한 backoff, 최대 시도, 비용 중복 방지 동작이 검증됨 |
| 5xx | 제한 재시도, 비재시도 오류 구분, 장애 격리와 정제 로그가 검증됨 |
| 비용 한도 | 요청·동시성·일 비용 상한과 초과 차단이 계약 단가 및 운영 정책과 일치함 |
| kill switch | 전역·현장 기능 중지와 승인 철회가 신규 외부 호출 전에 적용됨 |
| 법무 승인 | 적용 계약·개인정보·국외 이전·고객 데이터 조항의 승인자와 시각이 기록됨 |
| 고객 승인 | 고객·현장·provider·model·목적·원천 유형·만료가 명시된 승인이 기록됨 |

심사 착수 전에는 다음 증거 목록만 준비한다. provider 이름, 실제 증거 위치, 검토자, 승인일, 만료일이 정해지기 전에는 빈칸을 임의 값으로 채우지 않고 `PENDING`으로 둔다. `evidenceReference`에는 비밀값이나 고객 원문을 넣지 않고 접근 통제된 계약·보안·운영·고객 승인 대장의 문서 ID와 version만 기록한다.

| 체크 키 | 주 승인 영역 | 필요한 증거 |
| --- | --- | --- |
| `contract_terms` | 법무 | 적용 계약 version, 허용·금지 목적, 책임·재위탁·변경 통지 조항 |
| `data_retention` | 보안·법무 | 입력·출력·로그별 저장 위치/기간, 삭제 요청·계약 종료 삭제 절차와 확인 방식 |
| `training_use` | 법무·고객 | 입력·출력·metadata의 학습/개선 사용 조건, opt-out 적용 증거 |
| `transfer_region` | 보안·법무·고객 | 처리·저장·백업 지역, 국외 이전 근거와 고객 허용 범위 |
| `tls` | 기술·보안 | TLS 최소 버전, 인증서 검증, 비밀 저장·회전 시험 결과 |
| `timeout` | 기술 | 연결·응답 timeout 설정, 무한 대기 차단과 timeout 시험 결과 |
| `rate_limit_429` | 기술 | `Retry-After`/backoff, 최대 시도, 중복 비용 방지 시험 결과 |
| `server_error_5xx` | 기술 | 재시도 가능 오류 구분, 최대 시도, 장애 격리·정제 로그 시험 결과 |
| `cost_limit` | 기술·고객 | 단가 근거, 일 요청/동시성/비용 상한, 초과 차단과 알림 시험 결과 |
| `kill_switch` | 기술·보안 | 전역·현장 중지, 승인 철회 뒤 provider spy 호출 0건인 시험 결과 |
| `legal_approval` | 법무 | 승인 문서 ID/version, 승인자, 승인일, 만료·재검토일 |
| `customer_approval` | 고객 | 고객·현장·provider·model·목적·원천 유형, 승인자, 승인일, 만료·철회 조건 |

기술 책임자는 timeout·429·5xx·비용 계측·kill switch 증거를, 보안 책임자는 전송 지역·TLS·비밀 회전·보존 통제를, 법무 책임자는 계약·학습 사용·국외 이전·승인 만료를, 고객 승인 책임자는 허용 scope·원천 유형·철회 여부를 확인한다. 네 책임자의 실제 사용자 ID와 대리 절차는 고객별 비공개 운영대장에 실제 값이 정해진 뒤 기록한다. 현재 값은 모두 `PENDING`이다.

`ai_provider_onboarding_reviews`는 위 12개 항목과 기술·보안·법무·고객 네 영역의 `PENDING`/`APPROVED`/`REJECTED`, 검토자·검토 시각을 불변 review version으로 보존한다. 체크리스트 전건 `PASS`와 네 영역 `APPROVED`가 모두 있어야 provider 착수 게이트를 통과한다. 별도의 `ai_transfer_approvals`, 활성 프롬프트, 비용/timeout 정책, 기능 플래그와 kill switch는 이후에도 각각 유효해야 하며 이 심사 하나가 다른 통제를 대체하지 않는다. 현재 provider별 운영 client는 승인되지 않았으므로 기술·보안·법무·고객 상태를 모두 `PENDING`으로 해석하고 외부 호출을 계속 차단한다.

### Ground-truth dataset 권한·감사 경계

- 개별 ground-truth 사례의 첫 등록과 2차 승인은 보고서 작성 role인 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`에 허용한다. 첫 등록자는 첫 승인자가 되고, 같은 사용자의 2차 승인은 서버가 거부한다. `includePending=true` 조회는 운영 화면에서 대기 사례를 찾기 위한 것이며 사례를 활성화하거나 준비도에 포함하지 않는다.
- dataset 작성·구성·검토는 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`에 허용한다. 최종 2단계 승인은 `admin`, `system-admin`, `document-admin`, `department-manager`만 허용한다.
- 역할만으로 자기 승인을 허용하지 않는다. 작성자, 검토자, 1차 승인자, 2차 승인자의 사용자 ID가 모두 달라야 하며 서버가 상태 전이마다 검사하고 DB check constraint도 동일한 분리를 강제한다. WPF 버튼 비활성화는 안내일 뿐 서버 검사를 대체하지 않는다.
- 실제 현장 평가의 독립 표본 API와 WPF `24칸 독립 검토`는 보고서 작성 role인 `admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`에 허용한다. 서버는 승인 dataset snapshot hash로 24개 범주·유형 칸에서 1건씩 결정적으로 고정하며 다른 case 목록 제출을 거부한다. 두 검토자는 같은 표본을 독립 판정하며 서로 달라야 한다. 첫 판정의 `findings`와 `decisionHash`는 두 번째 검토 전까지 다른 사용자 응답과 WPF 비교 영역에서 숨긴다. 결과가 다르면 `PENDING_CONSENSUS`를 유지하고 앞선 두 사용자에게 합의 제출을 허용하지 않으며 다른 제3 검토자가 불일치 case 전체를 처리하기 전에는 provider 착수 게이트를 통과하지 않는다.
- WPF의 버튼 비활성화와 blind 표시는 안내·노출 최소화 계층이다. 최종 권한, 동일 표본, 두 검토자 분리, 합의자 분리, dataset/run/snapshot 결합은 FastAPI가 다시 검사한다. 표본 화면은 고객 원문을 별도 저장하지 않고 서버가 반환한 source/version/trace/content hash와 판정 메모만 다루며 메모에 개인식별정보나 비밀값을 복제하지 않는다.
- dataset 조회·구성 변경·상태 전이는 고객·현장·DB scope를 ID 조건과 함께 검사한다. 대체 version 생성은 라인과 준비도 계열까지 같아야 하므로 다른 scope의 ID를 이용한 교차 운영을 허용하지 않는다.
- 생성, 구성 변경, 검토 요청, 검토, 각 승인, 폐기는 `ai_operation_audit_events`에 actor, dataset version, 사유와 결과 상태를 남긴다. 승인 snapshot과 과거 evaluation run은 보존하며 앱 재시작이나 새 version 생성으로 덮어쓰지 않는다.
- 승인 dataset의 구성 변경은 `409`로 거부한다. 대체 version은 이전 승인본을 참조하고 최종 승인 때만 이전 상태를 `SUPERSEDED`로 전환한다. 이는 삭제가 아니며 과거 run의 dataset/hash 결합은 유지된다.
- 릴리스 readiness의 `FAIL/PENDING`은 외부 provider 요청 생성 단계에서 차단한다. 내부 후보 재생성·품질 점검은 민감정보 필터와 원천 권한을 계속 적용하면서 허용하고, 비AI 핵심 업무 API에는 readiness 의존성을 추가하지 않는다.

## 보존과 커밋 주의

보존과 커밋 제외는 충돌하지 않는다.

테스트 DB, 테스트 파일, 로그, 스모크 테스트 산출물, 렌더링 결과는 삭제하지 않는다. 이 파일들은 기능 검증 이력이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 로컬에 보존한다.

단, 실제 고객 문서, 운영 DB, 운영 파일 저장소, 운영 비밀값, 개인 로컬 경로, 빌드 결과, 배포 산출물은 Git에 올리지 않는다. 테스트 산출물도 PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/` 하위 파일을 Git 제외 대상으로 본다. SQLite와 WAL/SHM 보조 파일은 경로와 용도에 관계없이 로컬에 보존하되 Git으로 추적하거나 커밋하지 않는다.

커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 포함한 테스트 산출물, 스모크 테스트 산출물, 개인 로컬 경로, 운영 설정, 고객 파일이 포함되지 않았는지 검증한다.

## 아직 후속 범위인 보안 기능

- 고객 유사 네트워크의 HTTPS 인증서 발급·신뢰 배포·갱신·폐기, 방화벽과 시간 동기화 실기 검증. schema version 13 기계 판정표, WPF 폐기 확인과 복구 안내는 준비됐지만 승인 인증서·CRL/OCSP·실제 망·시험 사용자 접근성의 PASS 증거는 아직 없음
- 서버 접근 감사의 1년 보존·책임·정기 검토 기준을 현장 책임자가 승인하고 실제 조회·백업 복원·폐기를 실기로 검증
- 브라우저 직접 접근 제한 정책의 설치/배포 자동화
- Android MDM 제품 적용, 운영 인증서와 현장별 단말 등록·비활성화·교체 실기 검증
- Android Keystore/outbox 암호화와 foreground service의 Doze·재부팅·강제 중지 실단말 검사
- provider별 운영 계약·전송 지역 검증과 운영 네트워크 활성 절차. 현재 generic adapter는 명시적 test scope에서만 허용
- 운영 AI 감사 메타데이터의 장기 archive/purge와 legal hold 승인·모니터링 운영 절차. hold API·DB 계약은 구현되었지만 현장별 책임자·보존 근거 형식·장기 이관 절차는 확정하지 않음

운영 파일럿 전 보안 게이트, 책임자, 장애 중단 기준과 증거 보존 형식은 [실제 배포 리허설과 제한 현장 파일럿](./pilot-rehearsal.md)을 따른다. 앱 암호화와 별개로 MDM은 단말 전체 암호화, 6자리 이상 화면 잠금, 개발자 옵션·USB 디버깅·USB 파일 전송·ADB backup 차단, 알 수 없는 출처 차단, 원격 잠금·초기화, 앱 allowlist와 kiosk 자동 재실행을 강제한다. 정책 예외 단말은 운영 데이터 사용을 금지한다.

## 복구 시 fail-closed 동기화

- instance/epoch 변경, cursor 역행, 기존 binding과 다른 서버 URL은 정상 연결로 간주하지 않는다. WPF는 한글 차단 사유를 표시하고 관리자 승인 전 서버 mutation과 알림 polling을 중지한다.
- 복구 장애 실기의 unauthenticated sync manifest에는 익명 pilot run ID, backup set ID, 복구 승인 ID, 담당자 역할 ID만 둔다. 고객명, 담당자 실명, 로컬·서버 경로, 토큰과 승인 문서 원문은 넣지 않는다. 장애 코드와 이 식별자 중 하나라도 잘못되거나 빠지면 서버는 `503`, WPF는 fail-closed로 처리한다.
- `연결됨`은 HTTPS 응답과 서버 식별 확인일 뿐 `안전하게 수렴됨`을 뜻하지 않는다. WPF는 명시적 장애 run 승인 뒤 `POST_APPROVAL_RESTART_REQUIRED`, 정상 manifest read-back 뒤 `POST_APPROVAL_VERIFICATION_REQUIRED`를 표시한다. DB quick/integrity/FK, 공개 version 포인터, report source hash, cursor·message 처리, idempotency/mutation receipt, DB 참조 파일과 실제 파일의 경로·크기·SHA-256, 데이터 손실·중복 mutation·권한 우회 0건을 별도 증거로 확인한다.
- 네 장애는 정상 복구 run과도, 서로 간에도 다른 `fault_run_id`와 reconciliation run ID를 사용한다. 각 장애의 화면, WPF 차단·재개 로그, 서버 감사는 해당 `fault-runs/<fault_run_id>/` 아래에 분리해 보존하고 승인 전·실패 증거를 덮어쓰지 않는다.
- 서버 reconciliation 승인은 복구 연습 프로세스의 `FLOWNOTE_RESTORE_*` 환경값을 자동 변경하지 않는다. 승인 감사 저장 뒤 서버를 정상 종료하고 장애 표지를 제거한 다음 재시작하며, 정상 manifest read-back 전에는 WPF가 자동 전송이나 polling을 재개하지 않는다.
- reconciliation 생성·조회·승인은 `admin` 또는 `system-admin` 권한과 유효한 세션이 필요하다. manifest에는 식별자·계약 범위·cursor 외의 데이터나 비밀값을 싣지 않는다.
- `DIVERGED`는 자동 덮어쓰기하지 않고 충돌 원문, 양쪽 hash, 승인자와 사유를 남긴다. 처리 message_id, 실패 run, divergence row, 기존 큐를 삭제하여 복구하지 않는다.
- 관리자 승인 화면은 `CONFIRMED/ABSENT/DIVERGED` 원판정과 `REBOUND/REQUEUE/CONFLICT` 조치를 서로 다른 영역에 한글 설명과 함께 그대로 표시한다. 원판정은 아직 상태를 바꾸지 않은 관측 결과로 안내한다. 승인 직전에는 run별 조합·건수, 매핑·큐 변경, 보존되는 로컬 원천과 충돌 증거, 서버 정상 종료·장애 표지 제거·재시작·정상 manifest 확인 조건을 다시 확인한다. 관리자 승인 사유와 위험 확인을 모두 입력해야 승인 버튼을 활성화하며, 단순한 “확인” 버튼이나 연결 성공만으로 승인 또는 안전 수렴을 대체하지 않는다.
- 익명 `machine_id` 문자열이 서로 다르다는 사실만으로 실제 별도 PC를 증명하지 않는다. 복구 수집기는 OS 장비 식별값을 로컬에서 읽어 원문을 저장하지 않고 SHA-256만 남기며, 전후 hash가 같으면 fail-closed한다. 장비 배치 기록과 각 장비에서 직접 수집한 원본 manifest·화면·로그·감사의 시각과 hash도 함께 대조한다. 단일 장비의 폴더 복사나 임의 ID 변경은 파일럿 PASS 증거로 사용할 수 없다.
