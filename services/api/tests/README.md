# API Tests

이 디렉터리는 FlowNote FastAPI 서버 테스트를 보관한다.

## 현재 테스트 범위

- SQLite MVP 스키마 생성과 `schema_migrations` 기록
- DB 상태 확인 API
- 로그인, Bearer Access Token 발급, Refresh Token 발급, 현재 사용자 조회
- 만료된 Access Token 거부
- 로그아웃 세션 폐기
- Refresh Token 회전과 잘못된 토큰/재사용 토큰 거부
- 인증 누락, 비밀번호 오류, 비활성 계정 거부
- 문서 등록, 파일 저장, SHA-256, 크기, MIME/확장자 메타데이터
- 새 문서 버전 등록과 이전 최신 버전 `SUPERSEDED` 처리
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정, 공개 문서 조회
- 문서 태그 생성/교체와 태그 사전 조회
- 문서 쓰기, FieldComment 등록, 열람 로그 조회 권한 검증
- FieldComment 등록, 목록, 문서별 조회, 관리자 검토, 분석 상태 갱신
- FieldComment 첨부 등록/목록과 허용 확장자, 크기, 해시 기록
- 문서 열람 로그 등록/목록
- 작업순서 보드 생성, 항목 추가, 전체 순서 변경, 상태 변경, 이력, 알림 후보 기록
- 보고서 초안 생성 보조, 보고서 등록, 목록, 상세 조회

## 실행

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

테스트 SQLite DB, 로그, 테스트 업로드 파일, 생성 샘플 파일은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.
