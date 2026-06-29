# API Tests

이 폴더는 FlowNote FastAPI 서버 테스트를 보관한다.

## 현재 테스트 범위

- SQLite MVP 스키마 생성과 `schema_migrations` 기록
- DB 헬스체크 API
- 로그인 API, Bearer access token 발급, `/auth/me`
- 인증 누락/잘못된 비밀번호/비활성 계정 거부
- 문서 등록, 파일 저장, SHA-256, 크기, MIME/확장자 기록
- 새 문서 버전 등록과 기존 최신 버전 `SUPERSEDED` 처리
- 문서 상태 변경, 버전 상태 변경, 명시적 공개 버전 지정
- 공개 문서 목록과 공개 버전 조회
- 문서 태그 등록/교체와 태그 사전 조회
- 역할 기반 권한: 문서 쓰기, FieldNote 작성, 접근 로그 조회
- FieldNote 등록, 목록, 문서별 조회, 관리자 검토/분석 갱신
- FieldNote 첨부 등록/조회, 허용 확장자와 크기/해시 기록
- 문서 접근 로그 등록/조회
- 작업순서판 생성, 항목 추가, 전체 재정렬, 상태 변경, 이력/알림 후보 기록

## 실행

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
```

테스트 SQLite DB, 테스트 로그, 테스트 업로드 파일, 생성된 샘플 파일은 보존 대상이다. 사용자가 명시적으로 삭제를 지시하지 않는 한 삭제하지 않는다.
