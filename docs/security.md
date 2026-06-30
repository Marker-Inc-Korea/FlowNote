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
- FastAPI role 기반 문서 쓰기, FieldComment 작성, 접근 로그 조회, 보고서 작성 권한

## 계정과 role

개발/스모크 테스트용 기본 비밀번호는 `1234`이다. 운영 배포에서는 이 값을 그대로 쓰면 안 된다.

현재 role 기준:

- 사용자 관리는 WPF에서 `admin`, `system-admin`만 가능하다.
- 문서 등록과 작업순서 편집은 관리자 계열, 반장, 조장까지 허용한다.
- `team-member`, `viewer`는 문서 열람과 FieldComment 작성 중심이다.
- controlled copy 다운로드는 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`만 허용한다.

## 서버 인증

FastAPI 서버는 HMAC 서명 Bearer access token과 `auth_sessions` 테이블을 함께 사용한다.

- 로그인은 `auth_sessions` row를 만들고 access token과 refresh token을 반환한다.
- refresh는 같은 세션에서 `access_token_id`와 `refresh_token_hash`를 교체한다.
- refresh 후 이전 access token과 이전 refresh token은 거부된다.
- logout은 세션을 `REVOKED`로 변경한다.
- 보호 API는 세션 상태, 폐기 시각, access token ID, 만료 시각을 모두 검증한다.

운영 전에는 `FLOWNOTE_ACCESS_TOKEN_SECRET`을 현장별 비밀값으로 바꾸고 Git에 저장하지 않는다.

## 문서 열람 보호

WPF 문서 뷰어는 로컬 앱 계층에서 보호한다.

- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`로 자동 닫힘 시간을 조정한다.
- 설정값은 최소 5초, 최대 3600초 범위로 정규화된다.
- 닫힘 사유는 `window_closed`, `auto_closed`, `download_blocked` 등으로 기록한다.
- PDF는 WebView2 기반 표시를 우선하고 저장/다운로드 이벤트를 차단한다.
- 텍스트, 이미지, Excel은 앱 내부 읽기 전용 미리보기로 표시한다.

## 보존과 커밋 주의

테스트 DB, 테스트 파일, 로그, 스모크 테스트 산출물은 삭제하지 않는다. 단, 실제 고객 문서, 운영 DB, 비밀값, 개인 로컬 경로, 배포 산출물은 Git에 올리지 않는다.

## 아직 후속 범위인 보안 기능

- 운영 설치 시 최초 비밀번호 변경 강제
- 계정 잠금/비밀번호 재설정 운영 UI
- 관리자 강제 세션 폐기 UI
- HTTPS 또는 사내망 보호 배포 정책
- 서버 접근 감사 로그의 운영 정책
- 브라우저 직접 접근 제한 정책의 설치/배포 자동화
