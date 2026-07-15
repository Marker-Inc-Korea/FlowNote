# API Tests

이 디렉터리는 FlowNote FastAPI 서버 테스트를 보관한다.

범위와 수집 기준선은 2026-07-14 현재 테스트 코드 기준이다.

## 현재 테스트 범위

- SQLite MVP 스키마 생성과 `schema_migrations` 기록
- DB 상태 확인 API
- 로그인, Bearer Access Token 발급, Refresh Token 발급, 현재 사용자 조회
- 만료된 Access Token 거부
- 로그아웃 세션 폐기
- Refresh Token 회전과 잘못된 토큰/재사용 토큰 거부
- 인증 누락, 비밀번호 오류, 비활성 계정 거부
- Android 승인 단말 로그인, 마지막 접속 갱신, 단말 등록/변경/비활성화/폐기/교체, 기존 세션 폐기와 권한 검증
- 문서 등록, 파일 저장, SHA-256, 크기, MIME/확장자 메타데이터
- 새 문서 버전 등록과 이전 최신 버전 `SUPERSEDED` 처리
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정, 공개 문서 조회
- 문서 태그 생성/교체와 태그 사전 조회
- 문서 쓰기, FieldComment 등록, 열람 로그 조회 권한 검증
- FieldComment 등록, 목록, 문서별 조회, 관리자 검토, 분석 상태 갱신
- FieldComment 첨부 등록/목록과 허용 확장자, 크기, 해시 기록
- 문서 열람 로그 등록/목록
- controlled copy 전체 role 정책, 1회성·만료·사용자/세션 바인딩, Range·경로·크기·해시·감사 검증
- 작업순서 보드 생성, 항목 추가, 전체 순서 변경, 상태 변경, 이력, 알림 후보 기록
- 공통 채널 생성, 멤버 관리, 메시지 조회, 사용자별 알림 읽음 처리
- 인수인계 등록과 수신자별 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 상태 기록
- 보고서 초안 생성 보조, 보고서 등록, 목록, 상세 조회
- AI 검색 근거 후보 재생성, 목록 조회, 제외 사유, FieldComment 검토 준비도, 삭제 문서와 원천 누락 보고서 source 제외 품질 점검
- AI 검색 ground-truth 회귀 평가의 기대/제외 근거, 권한 필터, 네 원천 커버와 후보 ID·내용 hash·순위 재현성
- 외부 AI 질의의 기본 비활성, 금지 목적, 보고서 작성 role, 전송 승인·철회, 승인 프롬프트 불변성, 네 원천 권한 snapshot, 민감정보 마스킹/차단, 최소 payload byte 검사, 인용 검증과 응답 본문 미저장
- 고객·현장별 `ai_sensitive_data_policies` 활성 정책의 금칙어·고객 식별자 차단과 provider payload 원문 비노출
- 서버 계정 비밀번호 재설정, 잠금/비활성화, 계정 생성, role 변경 운영 스크립트와 수명주기 API 검증

## 실행

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

2026-07-15 현재 FastAPI 테스트 수집 기준은 101개이다. 저장소 루트의 `scripts/verify-preserved-tests.ps1`도 101개를 고정 기대하고 생성한 JUnit의 tests/failure/error 수를 다시 검사하므로, 테스트를 추가하거나 제거할 때는 의도된 변경인지 확인한 뒤 이 문서와 스크립트의 기준선을 함께 갱신한다. 수집 기준선 일치와 FastAPI 전체 pytest 통과를 확인하며, WPF Core 테스트·앱 빌드·통합 스모크, Android 단위 테스트·debug build와 Git 산출물 점검을 포함한 전체 표준 검증은 Windows 기준 환경에서 저장소 루트의 해당 스크립트로 별도 확인한다.

테스트 SQLite DB, 로그, 테스트 업로드 파일, 생성 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.
