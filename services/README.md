# Services

이 문서는 2026-07-22 현재 `services/api` 코드 기준이다. 구현되지 않은 서비스는 마지막 후속 범위에서만 예외로 다룬다.

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
- 본인 비밀번호 변경, 임시 비밀번호 강제 변경과 기존 세션 폐기
- 서버 계정 생성, 표시 이름·role·상태 변경, 임시 비밀번호 재설정, 활성 세션 조회·전체/개별 폐기 API와 감사 이력
- 승인 단말 등록, 목록/상세/마지막 접속 조회, 정보/상태 변경, 교체와 기존 세션 폐기
- 문서 등록, 목록, 상세, 버전 목록, 새 버전 등록
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정, 공개 문서 조회
- 문서 태그 등록, 목록, 교체
- FieldComment 원천 불변 등록, 목록, 상세, 단계형 관리자 검토, 담당자·기한, 최대 200건 일괄 변경, 원천 hash 감사와 품질 작업함/지표. 개별 검토는 `review_revision` 조건부 갱신과 mutation receipt를 사용
- FieldComment 사진/파일 첨부 등록과 목록, 부모 comment ID·요청/저장 파일 SHA-256 검증과 응답 유실 멱등 재시도
- 문서 열람 로그 등록과 목록
- 공개 문서 버전의 만료·1회성 controlled copy 다운로드와 요청/허용/완료/실패/차단 감사
- 작업순서 보드, 항목 추가, 순서 변경, 상태 변경, 이력 조회. 쓰기는 `board_revision`, mutation key·intent hash receipt, stale revision 조건부 갱신을 적용
- 작업순서 알림 후보 조회와 상태 변경
- 공통 채널 생성/조회, 채널 멤버 관리, 채널 메시지, 사용자별 알림 읽음 처리
- 인수인계 등록/조회와 수신자별 읽음/확인/후속 필요 상태 기록
- 서버 계정 생성·변경·임시 비밀번호 재설정, 강제 비밀번호 변경, 활성 세션 조회·폐기와 감사 기록
- 보고서 초안 생성 보조, 보고서 등록, 목록, 상세 조회. `report_revision`, 내용/source 집합 hash와 mutation receipt를 보고서·근거·선택적 생성 문서와 한 transaction에 저장
- AI 검색 전 단계의 근거 후보 재생성·목록·품질 점검, 독립 승인 ground-truth 사례, 불변 dataset version과 결합 오프라인 회귀 평가 API
- 외부 AI 질의 생성·조회, 기본 비활성, 보고서 작성 role, 허용 목적, 전송 승인, 프롬프트, 원천 권한·민감정보·최소 payload, 근거 snapshot, 인용 검증과 호출 감사 게이트
- `system-admin` 전용 외부 AI 운영 API: 전송 승인 생성·철회, 불변 프롬프트 검토·승인·활성화·폐기, 전역/현장 kill switch와 요청·동시성·timeout·비용·보존 정책, 고객·현장 scope별 정제 감사 조회/내보내기, 만료 보존 일괄·단일 즉시 실행, legal hold 설정·해제
- 서버 lifespan의 만료 보존 스케줄러: 기본 1시간 간격 실행, 설정으로 활성 여부와 간격 제어, 활성 legal hold 질의 제외
- FastAPI 서버 DB와 WPF 로컬 DB의 SQLite 스키마 경계 검사: WPF `documents`/`document_versions` 구조를 감지하면 서버 테이블 생성 전에 초기화 중단
- 서버 instance/epoch/API contract와 알림 high-water cursor manifest, 관리자용 WPF 큐 reconciliation 판정·승인·감사 API
- 초기·비상 운영용 서버 계정 생성, 비밀번호 재설정, 상태 변경, role 변경 스크립트

Android는 공개 문서 목록·상세 API와 승인 단말 전용 1회성 secure view grant/stream API를 사용한다. PDF/이미지/TXT는 앱 내부에서만 열고 controlled copy는 별도의 허용 role을 사용하는 Windows WPF 흐름으로 유지한다.

## 개발 기준

- 서버 프레임워크: FastAPI
- 메타데이터 DB: SQLite 우선
- 파일 저장소: 서버 로컬 `storage/`
- API 기본 경로: `/api/v1`

provider별 운영 연동을 통한 실제 외부 AI 검색/작업 조언, MES/ERP 연동, 서버 파일 감시 API는 후속 범위이다. AI 관련 현재 서비스는 `ai_search_candidates` read model 운영 API, `ai_search_evaluation_runs`/`ai_search_evaluation_cases` 회귀 결과 누적, `/api/v1/ai/queries` 안전장치·응답 검증, `/api/v1/ai-operations` 운영 제어면까지다. provider 경계는 정제 질의와 최소 발췌, 안정된 원천 ID/hash만 넘긴다. generic JSON 네트워크 adapter는 명시적 test 환경에서만 생성되며 provider별 운영 client는 구현하지 않았다.

provider 직전 게이트는 `ai_sensitive_data_policies`의 활성 고객·현장 정책을 읽어 금칙어와 고객 식별자를 원천 단위로 차단한다. 이 민감정보 정책의 등록·변경 API/UI는 현재 서비스 범위에 없다. 별도로 구현된 `ai_operational_policies` API/UI는 kill switch, 호출 한도, 보존 기간과 감사 내보내기 허용 여부를 관리한다.

운영 보조 도구 중 `scripts/verify-pilot-restore.py`는 서버 쓰기 중지·SQLite checkpoint 뒤 서버 DB와 `storage`의 복구 전후 증거를 수집·비교한다. 이 도구는 DB 무결성, 테이블별 row 수와 파일 manifest를 확인하지만 별도 PC 복구 및 업무 시나리오 검증을 대신하지 않는다.

테스트 DB, 테스트 업로드 파일, 로그, 생성 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.
