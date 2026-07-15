# FlowNote 보안

이 문서는 2026-07-15 현재 코드에 적용된 통제와 운영 전 후속 통제를 구분한다.

## 현재 구현

현재 코드에 구현된 보안 기능은 다음과 같다.

- WPF 시작 시 로그인 요구
- WPF 로컬 계정 상태 `ACTIVE` 확인
- WPF role 기반 문서 등록, 파일 감시, 사용자 관리, 다운로드 허용 제어
- 문서 뷰어 자동 닫힘
- 다운로드 차단 시 로컬 접근 로그와 활동 이력 기록
- FastAPI 로그인, access token, refresh token, logout
- FastAPI `auth_sessions` 기반 세션 폐기와 token 교체 검증
- FastAPI 서버 계정 생성·role/상태 변경·임시 비밀번호 재설정·세션 조회/폐기 API와 변경 사유 감사
- WPF 서버 계정 운영 화면과 `must_change_password` 로그인 직후 비밀번호 변경 강제
- FastAPI role 기반 문서 쓰기, 태그 생성, FieldComment 작성, 접근 로그 조회, 보고서 작성 권한
- FastAPI 공개 문서 버전 controlled copy 1회성 티켓, 사용자·세션 바인딩, 만료·재사용 차단, 경로·크기·SHA-256 검증과 전체 감사
- FastAPI 채널 멤버십 기반 채널 메시지 조회, 사용자별 알림 읽음, 인수인계 수신 확인 권한
- Android 승인 단말 `deviceId` 로그인 검증과 `auth_sessions.device_id` 기록
- FastAPI 관리자 승인 단말 등록·상태·교체 API와 WPF 승인 단말 운영 화면
- WPF 채널함, 채널 관리, 인수인계 확인 현황 화면의 서버 인증/멤버십 기반 조회와 상태 변경
- Android 현장 단말 앱의 서버 Bearer token 사용, FieldComment/사진 outbox 재전송, 알림 읽음/인수인계 확인, 서버 오류 원문 비노출
- 외부 AI 질의의 보고서 작성 role(`admin`, `system-admin`, `document-admin`, `manager`, `assistant-manager`, `department-manager`) 제한, 기본 비활성 플래그, 허용 목적, 고객·현장·provider·model 전송 승인, 승인된 프롬프트와 근거 원천 상태 검사
- 외부 AI 질의·근거 snapshot·인용·호출 시도 감사 row, 기본 응답 본문 미저장과 응답 hash 저장
- `system-admin` 전용 외부 AI 전송 승인·불변 프롬프트 수명주기·전역/현장 kill switch와 한도·보존 정책 API 및 WPF 운영 화면
- 질의·응답·비밀 원문을 제외한 AI 운영 감사 조회/정책 허용 CSV와, 만료 질의 payload 비식별화·응답 원문 삭제의 수동 보존 처리 감사

Android 현장 단말과 Windows/Android 채널 화면은 현재 최소 구현이 들어와 있다. Android 문서 기능은 공개 목록·상세 메타데이터 조회까지이며 파일 본문 다운로드·미리보기는 구현되어 있지 않다. 공통 채널 API는 서버 로그인, role, 채널 멤버십으로 접근을 제한하며, Android 로그인은 승인된 `terminal_devices.device_id`와 `status = ACTIVE`를 요구한다. 승인 단말 등록, 비활성화, 폐기, 교체는 `admin`, `system-admin` 전용 API와 WPF 운영 화면에서 수행하고 `activity_history`에 변경 주체와 사유를 남긴다. Android의 로그인, 문서, 알림, 인수인계 화면은 예외 메시지와 서버 오류 본문을 그대로 노출하지 않고 연결 실패, 시간 초과, HTTP 401·403·404와 기타 HTTP 오류를 한글 현장 안내로 변환한다. Android는 개인 휴대폰 기본 배포가 아니라 승인된 현장 태블릿 또는 러기드 단말을 기준으로 한다. MDM, 운영 인증서, outbox 암호화 정책은 후속 보안 범위다.

## 계정과 role

개발/스모크 테스트용 기본 비밀번호는 `1234`이다. 운영 배포에서는 이 값을 그대로 쓰면 안 된다.

운영 계정 기준:

- 서버 최초 관리자 계정은 서버 DB 초기화 시 생성되는 `admin` 계정이다.
- 운영 설치에서는 WPF 첫 서버 로그인 전에 서버 PC에서 `admin`의 비밀번호를 현장 비밀번호로 변경한다.
- 서버 로그인한 `admin`, `system-admin`은 WPF 서버 계정 화면과 `/api/v1/server-accounts`를 사용한다. 계정 생성과 비밀번호 재설정은 8자 이상 임시 비밀번호와 필수 변경 사유를 받고 `must_change_password = true`로 저장한다.
- `must_change_password = true`인 사용자는 로그인 직후 WPF 비밀번호 변경 화면으로 이동하며, 서버도 변경 API 이외의 보호 API와 refresh를 거부한다. 변경 성공 시 모든 활성 세션을 폐기하고 새 비밀번호 재로그인을 요구한다.
- 서버 DB 운영 스크립트는 최초 관리자 변경과 비상 운영 경로로 유지한다. 스크립트는 대화식 비밀번호 입력을 사용하고 8자 미만 비밀번호를 거부하지만 API와 달리 임시 비밀번호 강제 변경 플래그를 설정하지 않으므로 일반 계정 운영은 WPF/API를 우선한다.
- 로컬 로그인에서 여는 WPF 사용자 관리 화면은 로컬 SQLite 계정 전용이다. 서버 계정 화면과 로컬 계정 화면은 서로의 계정을 변경하지 않는다.
- 서버 URL이 설정된 WPF에서 서버가 401 또는 403을 반환하면 로컬 계정 로그인으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.

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
- controlled copy 다운로드는 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.

서버-WPF role 정합성 기준:

- 문서 등록, 문서 버전 등록, 태그/상태 변경은 FastAPI `DOCUMENT_WRITE_ROLES`와 WPF `CanRegisterDocuments`를 같은 집합으로 유지한다.
- FieldComment 작성은 FastAPI `FIELD_COMMENT_CREATE_ROLES`와 WPF `CanWriteFieldComments` 모두 기본 role 전체를 허용한다.
- 접근 로그 조회와 사용자 관리는 `admin`, `system-admin`만 허용한다.
- 보고서 작성과 controlled copy 다운로드는 `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.
- WPF는 서버 로그인 성공 시 서버 응답의 사용자 ID, 표시 이름, role을 현재 세션 기준으로 사용한다. 서버가 401 또는 403을 반환하면 같은 로그인 ID의 로컬 계정으로 fallback하지 않는다.
- WPF 스모크 테스트는 같은 로그인 ID의 로컬 `system-admin` 계정과 서버 `team-member` 응답을 비교해 서버 role이 버튼 권한에 우선 적용되는지 검증한다.

## 서버 인증

FastAPI 서버는 HMAC 서명 Bearer access token과 `auth_sessions` 테이블을 함께 사용한다.

- 로그인은 `auth_sessions` row를 만들고 access token과 refresh token을 반환한다.
- refresh는 같은 세션에서 `access_token_id`와 `refresh_token_hash`를 교체한다.
- refresh 후 이전 access token과 이전 refresh token은 거부된다.
- logout은 세션을 `REVOKED`로 변경한다.
- 보호 API는 세션 상태, 폐기 시각, access token ID, 만료 시각을 모두 검증한다.
- 현재 예외로 `GET /api/v1/tags`는 인증 없이 태그 목록을 조회할 수 있고, 태그 생성은 문서 쓰기 role을 요구한다.
- WPF는 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정 로그인으로 우회하지 않는다.
- 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 WPF 로컬 계정 로그인을 사용한다.

운영 전에는 `FLOWNOTE_ACCESS_TOKEN_SECRET`을 현장별 비밀값으로 바꾸고 Git에 저장하지 않는다. 서버 운영 DB와 서버 `storage\`는 같은 서버 PC의 로컬 디스크에 두되, 서버 실행 계정과 운영 관리자만 접근할 수 있게 NTFS 권한을 제한한다. 계정 발급, 비밀번호 재설정, 비활성화 절차는 [배포 문서의 운영 계정 발급과 변경 절차](./deployment.md#운영-계정-발급과-변경-절차)를 따른다.

## 문서 열람 보호

WPF 문서 뷰어는 로컬 앱 계층에서 보호한다.

- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`로 자동 닫힘 시간을 조정한다.
- 설정값은 최소 5초, 최대 3600초 범위로 정규화된다.
- 닫힘 사유는 `window_closed`, `auto_closed`, `download_blocked` 등으로 기록한다.
- PDF는 WebView2 기반 표시를 우선하고 저장/다운로드 이벤트를 차단한다.
- 텍스트, 이미지, Excel은 앱 내부 읽기 전용 미리보기로 표시한다.
- TXT/PDF/XLSX/이미지의 정상, 비정상, 한글 파일명, 큰 파일 기준과 CAD/HWP 제외 범위는 [문서 미리보기 안정화 기준](../apps/windows/docs/document-preview-stability.md)을 따른다.

허용 role의 controlled copy도 로컬 원본을 직접 복사하지 않는다. WPF는 서버에 현재 문서/버전의 티켓을 요청하고 같은 Bearer 사용자·로그인 세션으로 한 번만 스트리밍한다. 서버는 공개 상태와 정확한 공개 버전, 저장소 경계, 파일 크기, 등록 SHA-256을 발급 전과 전송 전에 검사한다. 티켓 원문은 DB에 저장하지 않고 SHA-256만 보존하며 기본 60초 후 만료된다. Range 요청, 다른 사용자·세션, 재사용과 만료 후 요청은 거부되고 성공·실패·차단을 모두 감사한다. 응답은 서버 로컬 경로나 `storage_key`를 노출하지 않는다.

## 운영 데이터 보호

운영 기준 경로와 백업 대상은 [배포 문서](./deployment.md)를 따른다.

- 서버 SQLite, 서버 `storage\`, WPF 로컬 SQLite, WPF `Files\`는 운영 데이터이다.
- 운영 `.env`, 서비스 환경 변수, token secret, 비밀번호, 고객 문서는 Git에 올리지 않는다.
- 서버 PC 방화벽은 승인된 Windows WPF 클라이언트와 Android 현장 단말이 접근할 FastAPI 포트만 허용한다.
- 일반 브라우저 직접 접근은 초기 운영 기준이 아니며 승인된 설치형 클라이언트 접근을 기본으로 한다.
- Windows와 Android 채널 알림은 업무 채널, 서버 사용자, role, 클라이언트/단말 승인 상태를 기준으로 표시한다. 개인 메신저 대화 수집, 개인 휴대폰 기본 배포, GPS/근태 추적은 포함하지 않는다.
- 채널·인수인계 알림의 초기 전달은 외부 인터넷에 의존하지 않는 사내망 HTTPS polling이다. 서버는 Bearer token과 활성 채널 멤버십을 매 요청 검증한다. Android는 사용자별 마지막 cursor를 로컬 설정에 보존하고, WPF는 credential을 제외해 정규화한 서버 scope와 사용자 ID별 cursor·처리 `message_id`를 로컬 SQLite에 격리한다. 읽음 변경과 로컬 재처리는 공개 `message_id`를 멱등 키로 사용한다.
- Windows와 Android의 전경 polling은 기본 15초, 연결 실패 시 최대 120초 백오프를 적용한다. 401 응답에는 polling을 멈추고 토큰을 재사용하지 않으며 재로그인을 안내한다. 앱 비활성 상태에는 전경 polling을 중단한다.
- Android는 1차 범위에서 상시 백그라운드 서비스나 외부 push를 사용하지 않는다. 후속 WorkManager 확인은 승인 단말 정책, 네트워크 조건, Doze와 배터리 최적화 영향을 반영해야 하며 보안 알림의 즉시 전달 수단으로 가정하지 않는다.
- WebSocket과 외부 push는 후속 선택지다. WebSocket은 사내 프록시·재연결 운영 기준이, 외부 push는 인터넷 허용·외부 전송 데이터 최소화·고객 보안 승인이 각각 선행되어야 한다.
- 백업 저장소에도 운영 DB, 고객 문서, 비밀값이 포함되므로 접근 권한을 운영 관리자에게 제한한다.

## 외부 AI 전송과 운영자 승인

외부 AI 호출은 기본 비활성화하며 서버 설치나 provider 자격증명 등록만으로 켜지지 않는다. `FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false`가 기본이고, 이 값을 켜더라도 고객·현장·provider·model·목적·source type이 일치하는 미만료·미철회 승인, 승인·활성 프롬프트, 전역/현장 kill switch와 운영 한도를 모두 통과해야 한다. 승인·프롬프트·정책·감사·보존 API와 WPF `AI 운영` 화면은 `system-admin`만 사용한다.

- 고객의 서면 외부 전송 허용 범위, 허용 현장과 원천 유형, 승인 만료일
- provider와 model, 전송·처리 지역, 암호화, 보존 기간, 재위탁자, 입력/출력의 학습 사용 금지와 삭제 조건
- 승인된 프롬프트 버전, 응답 저장 방식, 사고 대응 연락처와 승인 철회 절차
- 시험 질의의 근거 인용 검증과 고객 담당자 확인

FlowNote의 `PUBLISHED`는 현장 사용자에게 공개되었다는 뜻이지 외부 사업자 전송 승인이 아니다. 고객 문서와 그 일부, FieldComment, 사진/OCR, 작업순서 이력, 보고서 근거는 고객 승인 없이는 모두 외부 전송 금지다. 승인 후에도 비밀번호·API key·token·인증서/개인키, 주민등록번호·금융/건강정보 등 고유·민감 개인정보, 고객이 대외비/수출통제/영업비밀로 지정한 내용, 얼굴·차량번호 등 불필요한 식별정보, `EXCLUDED`/`ARCHIVED` FieldComment, 삭제·비공개 문서와 승인 범위 밖 현장 데이터는 전송하지 않는다.

질의 생성 코드는 query snapshot 시점에 고객·현장 승인, source type, 원천 상태, 작성자 계정 상태·role과 연결 채널 멤버십을 다시 검사한다. 외부 전송 대상 FieldComment는 `ANALYZED`, `REVIEWED`, `SELECTED`로 제한하고, 문서는 삭제되지 않은 현재 공개 버전, 작업순서는 존재하는 변경 이력, 보고서는 비보관 보고서와 유효한 실제 source만 적격으로 선택한다. provider/model/system prompt는 서버 설정과 승인 프롬프트에서 선택하므로 사용자가 임의로 바꿀 수 없다.

provider 경계는 필터를 통과한 질의와 제한 길이의 최소 발췌, candidate/source/version/trace ID, content hash, rank, prompt version, 고정 출력 형식만 받는다. 전체 파일·사진·첨부, 사용자명, 로컬 경로, 내부 URL과 제외 원천은 전달하지 않는다. 사용자 질의의 주민등록번호·전화번호·이메일은 대체 표식으로 마스킹한다. 원천의 주민등록번호·전화번호·이메일, 계정·비밀번호·API key·token·로컬 경로·고객 식별자, prompt injection 지시와 `ai_sensitive_data_policies`의 현장별 금칙어는 검색 후보 생성 단계에서 원천 전체를 제외한다. 차단 원문은 후보, 일반 로그와 근거 snapshot에 남기지 않는다.

provider 응답은 크기 제한 안의 완전한 JSON이어야 하며 claim마다 중복 없는 기존 candidate ID가 필요하다. 서버는 숫자, 핵심 토큰 겹침, 부정 극성을 규칙으로 대조하고 summary도 인용된 근거 전체와 다시 확인한다. 모델 자기평가만으로 의미 일치를 승인하지 않는다. 낮은 확신은 `humanReviewRequired` 정상 보류, 명백한 모순·인용 오류·prompt injection은 본문 전체 폐기다. provider 응답 뒤에는 승인, kill switch/한도, 원천 상태·hash, 사용자 열람 권한을 재조회하며 바뀐 결과는 저장하거나 노출하지 않는다.

질의와 저장이 승인된 응답 본문은 제한 데이터로 취급한다. 생성·조회 API는 보고서 작성 role만 사용하며, 조회 API는 질의·응답 본문·citation 목록을 반환하지 않고 질의 상태·응답 hash·적격/제외 근거 snapshot만 반환한다. 현재는 호출자 본인만 조회하도록 제한하지 않으므로 관리자 간 질의 조회 범위는 운영 provider 연동 전에 정해야 한다. 일반 서버/프록시 로그에는 질의, 프롬프트, 근거 본문, 응답, 자격증명, 검출한 금칙 원문이나 provider raw 오류를 남기지 않는다.

질의 원문과 저장 승인 응답은 기본 90일이며 `DO_NOT_STORE`는 응답 hash만 남긴다. 만료 스케줄러는 질의 payload를 `[EXPIRED]`로 비식별화하고 응답 원문을 삭제하되 query/response hash, 근거·인용·호출 메타데이터와 외래키를 보존한다. 처리 건마다 `ai_retention_audits`에 삭제·비식별화 동작을 남긴다. 시스템 관리자 감사 API와 CSV는 질의·응답·근거 원문, 프롬프트 본문, provider raw 오류와 비밀값을 반환하지 않는다.

승인 만료, 고객 요청, provider 조건 변경, 정보 유출 의심이 발생하면 운영자는 기능 플래그를 끄고 승인을 철회해 신규 호출을 즉시 차단한다. 기존 원천과 `ai_search_candidates`는 삭제하지 않으며 외부 호출 없는 후보 재생성·목록·품질 점검은 계속 동작한다. 사고 분석에는 정제된 감사 로그를 사용하고 provider에 보낸 원문을 일반 로그에서 복구하려 하지 않는다.

## 보존과 커밋 주의

보존과 커밋 제외는 충돌하지 않는다.

테스트 DB, 테스트 파일, 로그, 스모크 테스트 산출물, 렌더링 결과는 삭제하지 않는다. 이 파일들은 기능 검증 이력이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 로컬에 보존한다.

단, 실제 고객 문서, 운영 DB, 운영 파일 저장소, 운영 비밀값, 개인 로컬 경로, 빌드 결과, 배포 산출물은 Git에 올리지 않는다. 테스트 산출물도 PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/` 하위 파일을 Git 제외 대상으로 본다. SQLite와 WAL/SHM 보조 파일은 경로와 용도에 관계없이 로컬에 보존하되 Git으로 추적하거나 커밋하지 않는다.

커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 포함한 테스트 산출물, 스모크 테스트 산출물, 개인 로컬 경로, 운영 설정, 고객 파일이 포함되지 않았는지 검증한다.

## 아직 후속 범위인 보안 기능

- HTTPS 또는 사내망 보호 배포 정책
- 서버 접근 감사 로그의 운영 정책
- 브라우저 직접 접근 제한 정책의 설치/배포 자동화
- Android MDM, 운영 인증서와 현장별 단말 등록·비활성화·교체 정책
- Android outbox 암호화와 제한된 WorkManager 백그라운드 알림 정책 검증
- provider별 운영 계약·전송 지역 검증과 운영 네트워크 활성 절차. 현재 generic adapter는 명시적 test scope에서만 허용
- 운영 AI 감사 메타데이터의 장기 archive/purge와 법적 보존 hold 정책
