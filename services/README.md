# Services

FlowNote 서버 구성 요소를 보관하는 영역이다.

## 범위

- `api/`: Python FastAPI 기반 REST API 서버

## 현재 구현

`services/api/`는 SQLite 기반 FastAPI 서버의 현재 구현이다.

- 상태 확인과 DB 연결 확인
- 개발 기본 관리자 계정 시드
- 로그인, Access Token 발급, Refresh Token 회전
- 로그아웃 시 `auth_sessions` 세션 폐기
- 현재 사용자 조회
- 승인 단말 등록, 목록/상세/마지막 접속 조회, 정보/상태 변경, 교체와 기존 세션 폐기
- 문서 등록, 목록, 상세, 버전 목록, 새 버전 등록
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정, 공개 문서 조회
- 문서 태그 등록, 목록, 교체
- FieldComment 등록, 목록, 상세, 관리자 검토, 분석 상태 갱신
- FieldComment 사진/파일 첨부 등록과 목록
- 문서 열람 로그 등록과 목록
- 공개 문서 버전의 만료·1회성 controlled copy 다운로드와 요청/허용/완료/실패/차단 감사
- 작업순서 보드, 항목 추가, 순서 변경, 상태 변경, 이력 조회
- 작업순서 알림 후보 조회와 상태 변경
- 공통 채널 생성/조회, 채널 멤버 관리, 채널 메시지, 사용자별 알림 읽음 처리
- 인수인계 등록/조회와 수신자별 읽음/확인/후속 필요 상태 기록
- 보고서 초안 생성 보조, 보고서 등록, 목록, 상세 조회
- AI 검색 전 단계의 근거 후보 재생성, 목록, 품질 점검과 오프라인 ground-truth 회귀 평가 API
- 외부 AI 질의 생성·조회, 기본 비활성, 관리자 role, 허용 목적, 전송 승인, 프롬프트, 근거 snapshot, 인용 검증과 호출 감사 골격
- 서버 계정 생성, 비밀번호 재설정, 상태 변경, role 변경 운영 스크립트

Android가 사용하는 공개 문서 API는 목록과 상세 메타데이터를 반환한다. 현재 Android 클라이언트에는 서버 문서 파일 본문 다운로드·미리보기 구현이 없고, controlled copy는 허용 role의 Windows WPF 흐름으로만 연결되어 있다.

## 개발 기준

- 서버 프레임워크: FastAPI
- 메타데이터 DB: SQLite 우선
- 파일 저장소: 서버 로컬 `storage/`
- API 기본 경로: `/api/v1`

운영 provider client를 통한 실제 외부 AI 검색/작업 조언, MES/ERP 연동, 관리자 강제 세션 폐기 UI, 서버 파일 감시 API는 후속 범위이다. AI 관련 현재 서비스는 `ai_search_candidates` read model 운영 API, `ai_search_evaluation_runs`/`ai_search_evaluation_cases` 회귀 결과 누적, `/api/v1/ai/queries` 안전장치·감사 골격까지다. 질의 라우터의 주입 경계는 질의/DB 원문 대신 hash·프롬프트 버전 ID·후보 ID만 넘기며, 저장소에는 네트워크 provider client가 없다.

테스트 DB, 테스트 업로드 파일, 로그, 생성 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.
