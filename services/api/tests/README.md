# API Tests

이 디렉터리는 FlowNote FastAPI 서버 테스트를 보관한다.

범위와 수집 기준선은 2026-07-31 현재 테스트 코드 기준이다.

## 현재 테스트 범위

- SQLite MVP 스키마 생성과 `schema_migrations` 기록
- WPF 로컬 `documents`/`document_versions` schema를 서버 DB로 지정했을 때 초기화 거부와 서버 전용 테이블 미생성
- DB 상태 확인 API
- 로그인, Bearer Access Token 발급, Refresh Token 발급, 현재 사용자 조회
- 만료된 Access Token 거부
- 로그아웃 세션 폐기
- Refresh Token 회전과 잘못된 토큰/재사용 토큰 거부
- 인증 누락, 비밀번호 오류, 비활성 계정 거부
- Android 승인 단말 로그인, 마지막 접속 갱신, 단말 등록/변경/비활성화/폐기/교체, 기존 세션 폐기와 권한 검증
- 문서 등록, 파일 저장, SHA-256, 크기, MIME/확장자 메타데이터
- 새 문서 버전 등록과 이전 최신 버전 `SUPERSEDED` 처리
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정, 공개 문서 조회, 공개·상태·태그 mutation receipt 재생과 key 재사용 충돌
- 문서 태그 생성/교체와 태그 사전 조회
- 문서 쓰기, FieldComment 등록, 열람 로그 조회 권한 검증
- FieldComment 등록, 목록, 문서별 조회, 원천 불변·삭제 차단, 단계형 관리자 검토, 담당자·기한, 최대 200건 일괄 처리, 원천 hash 감사와 품질 작업함/지표
- FieldComment 검토 revision의 동시 요청 1건만 성공, 같은 mutation receipt 재생, 오래된 revision·다른 intent key 재사용 차단
- FieldComment 첨부 등록/목록과 허용 확장자, 크기, 부모 ID·요청/실파일 SHA-256 검증, 응답 유실 뒤 같은 key 재시도 시 첨부/file object 1건 유지
- 문서 열람 로그 등록/목록
- controlled copy 전체 role 정책, 1회성·만료·사용자/세션 바인딩, Range·경로·크기·해시·감사 검증
- 작업순서 보드 생성, 항목 추가, 전체 순서 변경, 상태 변경, 이력, 알림 후보 기록
- 작업순서 mutation의 revision 증가·no-op 거부, 동일 key 재시도, key의 다른 intent 재사용 거부, 동일 revision 두 client 경쟁의 1건만 성공, API 재시작 후 receipt 재사용
- 공통 채널 생성, 멤버 관리, 메시지 조회, 사용자별 알림 읽음 처리
- 인수인계 등록과 수신자별 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 상태 기록
- 보고서 초안 생성 보조, 보고서 등록, 목록, 상세 조회, report revision·내용/source 집합 hash·mutation receipt와 생성 문서 transaction
- 선정 뒤 바뀌거나 사라진 보고서 source, 오래된 report revision, 내용/source 집합 hash 불일치와 다른 intent key 재사용 차단
- AI 검색 근거 후보 재생성, 목록 조회, 제외 사유, FieldComment 검토 준비도, 삭제 문서와 원천 누락 보고서 source 제외 품질 점검
- AI 검색 ground-truth 회귀 평가의 기대/제외 근거, 권한 필터, 네 원천 커버와 후보 ID·내용 hash·순위 재현성
- scope별 ground-truth 사례의 원천 provenance 고정·독립 2인 승인과 불변 dataset version 작성·검토·2단계 승인·대체·폐기·평가 결합
- 승인된 실제 익명 현장 dataset의 동일 snapshot 평가 2회 확인, 24칸 독립 표본 판정 은닉·비교와 불일치 제3 합의
- 외부 AI 질의의 기본 비활성, 금지 목적, 보고서 작성 role, 전송 승인·철회, 승인 프롬프트 불변성, 네 원천 권한 snapshot, 민감정보 마스킹/차단, 최소 payload byte 검사, 인용 검증과 응답 본문 미저장
- 고객·현장별 `ai_sensitive_data_policies` 활성 정책의 금칙어·고객 식별자 차단과 provider payload 원문 비노출
- fake/recording/제한형 network adapter의 성공·timeout·429/5xx 재시도·비재시도 오류, 응답 구조·크기·중복·prompt injection·의미 일치 검증
- `system-admin` 외부 AI 승인·프롬프트·정책·감사·CSV·보존 API, 고객·현장 scope 격리, 자동/일괄/단일 만료, legal hold 설정·해제·만료 차단과 정제 감사 보존
- 서버 계정 비밀번호 재설정, 잠금/비활성화, 계정 생성, role 변경 운영 스크립트와 수명주기 API 검증
- 서버 instance ID 안정성·명시적 epoch 증가, sync manifest, WPF 큐 inventory의 `CONFIRMED`/`ABSENT`/`DIVERGED` 판정, 관리자 승인 적용과 divergence 감사 보존, 복구 장애 유형별 독립 reconciliation run 검증

## 실행

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

2026-07-31 현재 FastAPI 테스트 코드와 저장소 루트 `scripts/verify-preserved-tests.ps1`의 guard는 164개로 일치한다. 새 4건은 민감정보 정책 수명주기, 승인 철회 직후 차단, provider 응답 중 사용자 role 변경, provider 응답 중 정책 철회를 검증한다. 스크립트는 수집 원본, 중복 목록, 종료 코드와 JUnit을 같은 `run_id`에 보존하며, 불일치나 도구 부족 때 현재 단계·기대값·실제값·보존된 데이터와 `.\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>` 명령을 안내한다. 전체 표준 검증은 Windows x64 기준 환경에서 옵션을 생략해 수행한다. FastAPI, WPF Core 테스트·앱 빌드·통합 스모크, Android 단위 테스트·debug build와 실행 전후 Git 산출물 점검을 같은 `run_id`에 보존하고, 무생략 실행 2회가 같은 clean 소스 커밋에서 모두 통과하기 전에는 유효한 기준선으로 판정하지 않는다.

테스트 SQLite DB, 로그, 테스트 업로드 파일, 생성 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.
