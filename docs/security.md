# FlowNote 보안

## 현재 구현

현재 코드에 구현된 보안 기능은 다음과 같다.

- WPF 시작 시 로그인 요구
- WPF 로컬 계정 상태 `ACTIVE` 확인
- WPF role 기반 문서 등록, 파일 감시, 사용자 관리, 다운로드 허용 제어
- 문서 뷰어 자동 닫힘
- 다운로드 차단 시 로컬 접근 로그와 활동 이력 기록
- FastAPI 로그인, access token, refresh token, logout
- FastAPI `auth_sessions` 기반 세션 폐기와 token 교체 검증
- FastAPI role 기반 문서 쓰기, 태그 생성, FieldComment 작성, 접근 로그 조회, 보고서 작성 권한
- FastAPI 채널 멤버십 기반 채널 메시지 조회, 사용자별 알림 읽음, 인수인계 수신 확인 권한

Android 현장 단말 보안과 Windows/Android 채널 전용 화면은 제품 방향에 포함하지만 아직 클라이언트 코드 구현 범위는 아니다. 공통 채널 API는 서버 로그인, role, 채널 멤버십으로 접근을 제한하며, 클라이언트/단말 승인 상태는 후속 클라이언트 구현에서 함께 사용한다. Android는 개인 휴대폰 기본 배포가 아니라 승인된 현장 태블릿 또는 러기드 단말을 기준으로 한다.

## 계정과 role

개발/스모크 테스트용 기본 비밀번호는 `1234`이다. 운영 배포에서는 이 값을 그대로 쓰면 안 된다.

운영 계정 기준:

- 서버 최초 관리자 계정은 서버 DB 초기화 시 생성되는 `admin` 계정이다.
- 운영 설치에서는 WPF 첫 서버 로그인 전에 서버 PC에서 `admin`의 비밀번호를 현장 비밀번호로 변경한다.
- 현재 구현 범위에는 첫 로그인 후 비밀번호 변경 강제 화면, 서버 계정 관리 API, WPF 서버 계정 관리 연동이 없다. 운영 기준은 “첫 로그인 전 비밀번호 변경”이며 앱 강제 변경은 후속 범위다.
- 서버 계정의 발급, 비밀번호 재설정, 잠금, 비활성화, 퇴사 처리는 서버 DB 운영 스크립트에서 수행한다. 현재 운영 스크립트는 대화식 비밀번호 입력을 사용하고 8자 미만 비밀번호를 거부한다.
- WPF 사용자 관리 화면은 로컬 SQLite 계정 전용이다. 화면 제목, 목록, 상세 영역의 “로컬” 표기를 운영 기준으로 유지하며 서버 계정을 생성, 재설정, 비활성화하지 않는다.
- 서버 URL이 설정된 WPF에서 서버가 401 또는 403을 반환하면 로컬 계정 로그인으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.

운영 전 비밀번호 변경 체크리스트:

- 서버 PC에서 `app.ops.server_accounts reset-password --username admin`으로 최초 서버 관리자 비밀번호를 변경한다.
- 새 비밀번호는 대화식 프롬프트에만 입력하고 명령줄 인자, 운영 기록, 로그에 적지 않는다.
- 변경 후 WPF 서버 로그인은 새 비밀번호로만 성공해야 한다.
- 기본 비밀번호 `1234`로 서버 로그인이 401로 실패할 때 WPF가 로컬 `admin / 1234` 계정으로 우회하지 않는지 확인한다.

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

## 운영 데이터 보호

운영 기준 경로와 백업 대상은 [배포 문서](./deployment.md)를 따른다.

- 서버 SQLite, 서버 `storage\`, WPF 로컬 SQLite, WPF `Files\`는 운영 데이터이다.
- 운영 `.env`, 서비스 환경 변수, token secret, 비밀번호, 고객 문서는 Git에 올리지 않는다.
- 서버 PC 방화벽은 승인된 Windows WPF 클라이언트와 Android 현장 단말이 접근할 FastAPI 포트만 허용한다.
- 일반 브라우저 직접 접근은 초기 운영 기준이 아니며 승인된 설치형 클라이언트 접근을 기본으로 한다.
- Windows와 Android 채널 알림은 업무 채널, 서버 사용자, role, 클라이언트/단말 승인 상태를 기준으로 표시한다. 개인 메신저 대화 수집, 개인 휴대폰 기본 배포, GPS/근태 추적은 포함하지 않는다.
- 백업 저장소에도 운영 DB, 고객 문서, 비밀값이 포함되므로 접근 권한을 운영 관리자에게 제한한다.

## 보존과 커밋 주의

보존과 커밋 제외는 충돌하지 않는다.

테스트 DB, 테스트 파일, 로그, 스모크 테스트 산출물, 렌더링 결과는 삭제하지 않는다. 이 파일들은 기능 검증 이력이므로 사용자가 명시적으로 삭제를 지시하지 않는 한 로컬에 보존한다.

단, 실제 고객 문서, 운영 DB, 운영 파일 저장소, 운영 비밀값, 개인 로컬 경로, 빌드 결과, 배포 산출물은 Git에 올리지 않는다. 테스트 산출물도 PDF, 이미지, Excel, TXT, 로그, 렌더링 결과, `data/local/Files/`, `Data/Files/` 하위 파일은 Git 제외 대상으로 본다. SQLite는 현재 `.gitignore` 예외에 따라 `data/local/**/*.sqlite`와 `services/api/data/**/*.sqlite`에 한해 테스트/개발 검증 DB로 추적될 수 있다.

커밋 전에는 `git status`와 staged 목록을 확인해 SQLite를 제외한 테스트 산출물, 스모크 테스트 산출물, 개인 로컬 경로, 운영 설정, 고객 파일이 포함되지 않았는지 검증한다.

## 아직 후속 범위인 보안 기능

- 첫 로그인 후 비밀번호 변경을 강제하는 서버 컬럼, API, WPF 화면
- 계정 잠금/비밀번호 재설정 운영 UI와 서버 계정 관리 API
- 관리자 강제 세션 폐기 UI
- HTTPS 또는 사내망 보호 배포 정책
- 서버 접근 감사 로그의 운영 정책
- 브라우저 직접 접근 제한 정책의 설치/배포 자동화
- Android 단말 등록, MDM 또는 현장 단말 관리 정책
- Windows/Android 채널 알림 전달 방식과 오프라인 임시 저장 암호화
