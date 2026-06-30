# FlowNote 보안 정책

## 0. 현재 코드 기준 보안 상태

현재 코드에서 실제 구현된 보안 기능은 Windows WPF 앱 시작 시 로그인 요구, 기본 계정 생성, 로그인 성공 후 화면 진입, 알림 대상 사용자 식별, 문서 보기 창 열림/닫힘 로컬 감사 로그, 설정 기반 뷰어 자동 닫힘, role 기반 문서 다운로드 차단과 `download_blocked` 감사 로그, FastAPI 로그인 API, 서버 저장 인증 세션, Bearer access token, refresh token 회전, logout 세션 폐기이다. `FLOWNOTE_API_BASE_URL`이 설정된 경우 WPF 로그인 화면은 FastAPI 로그인 API를 먼저 호출하고, 성공 응답의 사용자 ID, 사용자명, 역할, 표시명, access token, refresh token, 만료 시각을 로그인 결과로 보관한다. 서버 URL이 없거나 서버 로그인 호출이 실패하면 기존 로컬 SQLite 로그인을 유지한다. FastAPI 문서/FieldNote/문서 접근 로그 API는 `Authorization: Bearer {access_token}`이 없거나 유효하지 않거나, access token이 만료/대체/폐기되었으면 `401`을 반환한다. 서버는 role 값으로 문서 등록, 문서 버전 등록, 문서 태그 변경, 태그 등록, 문서 접근 로그 조회 권한을 검사하고 권한이 없으면 `403`을 반환한다. WPF는 로그인 role 기준으로 문서 등록/파일 업로드 버튼과 파일 드롭을 비활성화하고, 문서 뷰어의 controlled copy는 관리자급 다운로드 role에만 허용한다. 서버 감사 로그 자동 actor 지정 전체 적용, 외부 접속 제어는 아직 구현된 기능이 아니라 제품 보안 목표이다.

## 0.1 개발 접근 정보와 공개 저장소 주의

이 저장소는 공개 저장소가 될 수 있으므로 실제 사용자 계정, 비밀번호, 토큰, API 키, DB 접속 정보, 고객 문서, 운영 데이터, 개인 로컬 경로가 포함된 실행 설정은 커밋하지 않는다. 개발 또는 테스트 접근 정보가 필요하면 비밀값은 로컬 `.env`나 승인된 비밀 관리 위치에 두고, 문서에는 비밀이 아닌 기준만 남긴다.

테스트 파일, 테스트 SQLite DB, 테스트 결과 로그, 테스트 내역 문서는 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다. 테스트 환경 데이터는 운영 데이터가 아니지만, 현재 프로젝트에서는 기능 검증 이력으로 보존 대상이다.

## 0.2 서버 인증 방식

FastAPI 서버는 HMAC 서명 Bearer access token과 서버 저장 `auth_sessions` 테이블을 함께 사용한다. access token에는 사용자 ID, 세션 ID, access token ID, 발급/만료 시각을 담고, 서버는 `FLOWNOTE_ACCESS_TOKEN_SECRET`으로 서명을 검증한 뒤 `auth_sessions`의 세션 상태와 access token ID를 확인한다. access token 만료 시간은 `FLOWNOTE_ACCESS_TOKEN_EXPIRES_MINUTES`로 조정하며 기본값은 480분이다. refresh token 만료 시간은 `FLOWNOTE_REFRESH_TOKEN_EXPIRES_DAYS`로 조정하며 기본값은 14일이다.

`POST /api/v1/auth/login`은 세션을 만들고 access/refresh token을 발급한다. `POST /api/v1/auth/refresh`는 refresh token hash를 검증하고 같은 세션의 access token ID와 refresh token hash를 새 값으로 바꾼다. 따라서 이전 access token과 이전 refresh token은 재사용할 수 없다. `POST /api/v1/auth/logout`은 현재 access token의 세션을 `REVOKED`로 바꾼다.

운영 전에는 기본 서명 비밀값을 현장별 비밀값으로 교체하고, HTTPS 또는 사내망 보호, 권한별 접근 제어, 감사 로그 actor 자동 지정 정책을 함께 확정해야 한다.

## 0.3 개발용 계정과 운영 초기 비밀번호

개발용 기본 계정과 테스트 계정은 `admin / 1234` 또는 고정 비밀번호 `1234`를 사용한다. 이 정책은 로컬 개발과 스모크 테스트 전용이다. 운영 배포 전에는 다음 항목으로 분리한다.

- 서버 기본 관리자 계정은 현장별 초기 관리자 계정으로 재발급한다.
- 최초 로그인 시 비밀번호 변경을 요구한다.
- 초기 비밀번호는 저장소, 문서, 설치 파일에 고정값으로 남기지 않는다.
- 계정 잠금, 비밀번호 재설정, 퇴사/전보 계정 비활성화 절차를 운영 문서에 둔다.
- `FLOWNOTE_ACCESS_TOKEN_SECRET`은 현장별 비밀값으로 교체하고 저장소에 커밋하지 않는다.

## 1. 기본 원칙

FlowNote는 생산현장 문서를 다루므로 문서 유출 방지와 현장 단말기 보안을 기본 전제로 한다.

FlowNote의 배포 보안 원칙은 사내 서버형 운영이다. 문서와 파일은 우선 서버 PC의 SQLite DB와 로컬 storage 폴더에 저장하고, 현장/관리자 PC는 설치형 클라이언트로 접근한다.

- 모든 사용자는 회원 로그인 후 사용한다.
- 권한은 사용자, 역할, 그룹, 문서 권한을 기준으로 판단한다.
- 현장 사용자는 문서 열람과 코멘트 등록만 가능하다.
- 관리자급이 아닌 사용자 다운로드는 Windows WPF 클라이언트 앱에서 차단하고 `document_view_logs` 또는 `activity_history`에 `download_blocked`로 남긴다.
- 문서 뷰어 자동 닫힘은 WPF 클라이언트 앱에서 `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` 설정값 기준으로 동작한다. 미설정 기본값은 30초이다.
- 단말기는 클라이언트이며, 서버는 현장별로 구축한다.
- 운영 환경의 현장 사용자는 일반 브라우저 직접 접속이 아니라 승인된 Windows WPF 클라이언트 앱을 통해 사용한다.
- 서버 설치 위치는 고객 현장 또는 사내 서버 PC 1대를 기본으로 한다.
- 외부 접근은 초기 기본값이 아니며, 허용하는 경우 VPN, 방화벽, IP 제한, 인증 정책, 감사 로그를 전제로 한다.
- 문서 수정자, 열람자, 현장 코멘트 입력자, 실제 전달자 또는 작업자/작업그룹을 추적한다.
- 사진 기록 등록자, 작업순서 변경자, 작업순서 확인자와 상태 변경자를 추적한다.
- 작업자 추적 정보는 문서 효율성, 교육, 재발 방지, 이력 추적을 위한 운영 데이터로 관리한다.

## 2. 역할 기준

| 역할 | 설명 | 주요 권한 |
| --- | --- | --- |
| `admin`, `system-admin` | 시스템 관리자 | 문서 쓰기, 태그 변경, 접근 로그 조회, 후속 시스템 설정 |
| `manager`, `document-admin`, `assistant-manager`, `department-manager` | 관리자 그룹 | 문서 등록, 버전 등록, 태그 변경, FieldNote 등록 |
| `line-foreman` | 반장 | 문서 등록, 버전 등록, 태그 변경, FieldNote 등록 |
| `team-lead` | 조장 | 문서 등록, 버전 등록, 태그 변경, FieldNote 등록 |
| `team-member`, `viewer` | 조원/현장 사용자 | 문서 열람과 FieldNote 등록 중심. 문서 등록, 버전 등록, 태그 변경, 접근 로그 조회 불가 |

`download` 권한은 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`에만 부여한다. `line-foreman`, `team-lead`, `team-member`, `viewer`는 문서 열람과 FieldNote 흐름은 사용할 수 있지만 문서 파일 copy/download는 차단한다.

현재 서버 구현 기준 권한은 다음과 같다.

| 기능 | 허용 role | 거부 시 |
| --- | --- | --- |
| 문서 등록 `POST /api/v1/documents` | 관리자 그룹, `line-foreman`, `team-lead` 이상 | `403` |
| 문서 버전 등록 `POST /api/v1/documents/{documentId}/versions` | 관리자 그룹, `line-foreman`, `team-lead` 이상 | `403` |
| 문서 태그 변경 `PUT /api/v1/documents/{documentId}/tags` 및 태그 등록 `POST /api/v1/tags` | 관리자 그룹, `line-foreman`, `team-lead` 이상 | `403` |
| FieldNote 등록 `POST /api/v1/field-notes` | 인증된 관리자/반장/조장/조원 계정 | `401` 또는 미지원 role `403` |
| FieldNote 첨부 등록 `POST /api/v1/field-notes/{noteId}/attachments` | 인증 사용자. 현재 구현은 별도 role 제한 없이 인증을 요구 | `401` |
| 작업순서판 생성/항목 추가/정렬/상태 변경 | 관리자 그룹, `line-foreman`, `team-lead` 이상 | `403` |
| 접근 로그 조회 `GET /api/v1/documents/{documentId}/access-logs` | `admin`, `system-admin` | `403` |

## 3. 문서 열람 보안

현장 사용자는 승인된 앱의 뷰어에서 문서를 열람한다.

- 현재 단계에서는 문서 열람 자체를 불필요하게 막지 않는다.
- Windows WPF 클라이언트 앱은 문서 파일 직접 다운로드를 role 정책으로 차단한다.
- PDF는 WebView2 내부 뷰어를 사용하되 저장/다른 이름 저장/인쇄 툴바와 기본 컨텍스트 메뉴, 다운로드 시작 이벤트, 새 창 요청을 차단한다.
- Excel은 앱 내부 읽기 전용 `DataGrid`, 이미지는 WPF `Image`, 텍스트는 읽기 전용 `TextBox`로 표시하며 외부 실행 경로를 만들지 않는다.
- Windows WPF 클라이언트 앱에서 제한 시간이 지나면 뷰어를 자동 닫힘 처리한다.
- 자동 닫힘과 다운로드 차단 기록은 로컬 열람 로그와 전체 이력에 남기고, 서버 문서 ID가 매핑된 경우 문서 접근 로그 동기화 큐를 통해 FastAPI `document_access_logs`로 전송한다.

설정 항목:

- 기본 뷰어 제한 시간: `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`, 기본값 30초, 최소 5초, 최대 3600초
- 문서 유형별 제한 시간
- 역할별 제한 시간
- 자동 닫힘 경고 표시 시간

## 4. 관리자 다운로드

관리자급 사용자는 업무상 필요한 경우 문서 파일을 다운로드할 수 있다.

현재 WPF 앱의 `Save copy` 경로는 관리자급 다운로드 role에만 허용한다. 허용된 다운로드는 `activity_history`에 `document.downloaded`로 남기며, 차단된 시도는 `document_view_logs.close_reason=download_blocked`와 `activity_history.document.download_blocked`로 남긴다. 서버 문서 매핑이 있으면 `download_blocked` 접근 로그도 서버 동기화 후보가 된다.

다운로드 시 기록할 항목:

- 사용자 ID
- 단말기 ID
- 문서 ID
- 문서 버전 ID
- 다운로드 시각
- 클라이언트 IP

## 5. 앱 로컬 기능 보안

앱 로컬 기능은 Python FastAPI 서버가 직접 접근할 수 없는 단말기 기능만 제공한다.

- 고객 생산공장에서는 일반 브라우저 직접 접근을 기본 허용하지 않는다.
- 현장 사용자 단말기에서는 파일 감시 로컬 기능을 비활성화한다.
- 관리자 단말기에서만 파일 감시와 로컬 파일 선택을 허용한다.
- 로컬 기능 호출은 로그인 세션과 단말기 모드를 확인한다.
- 파일 감시, 로컬 파일 선택, 외부 뷰어 호출은 감사 로그 대상으로 둔다.

## 6. 감사 로그

다음 이벤트는 감사 로그 또는 접근 로그 대상으로 둔다.

- 로그인 성공/실패
- 문서 열람
- 뷰어 자동 닫힘
- 문서 다운로드 허용과 차단
- 권한 실패
- 문서 새 버전 업로드
- 현장 코멘트 등록, 사진 첨부 등록, 관리자 분석, 보고서 확정
- 작업순서 등록, 순서 변경, 상태 변경, 현장 TV 화면 조회
- 관리자 파일 감시 후보 생성
- 앱 로컬 기능 호출
- AI 조언 요청
