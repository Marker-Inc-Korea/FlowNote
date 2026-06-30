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

## 2026-06-30. 관리자 파일 감시

- 파일 감시는 WPF 네이티브 `FileSystemWatcher` 기반 로컬 기능이다.
- `admin`, `manager`, `system-admin`, `document-admin`, `assistant-manager`, `department-manager`만 사용할 수 있다.
- 감지된 파일은 즉시 업로드하지 않고 `file_watch_candidates`에 `PENDING`으로 저장한다.
- 확정 시 대상 문서, 버전명, 변경 사유가 필요하며 새 `document_versions` row를 만든다.

## 제품 범위 결정

- FlowNote는 MES/ERP를 대체하지 않는다.
- 문서 구조는 고객이 결정한다.
- BOM 문서 구조는 현장 표현 예시이며 기본 강제 구조가 아니다.
- AI 검색과 작업 조언은 충분한 데이터 축적 뒤 후속 기능으로 둔다.
- 초기 배포는 서버 PC 1대와 Windows 설치형 클라이언트를 기준으로 한다.
