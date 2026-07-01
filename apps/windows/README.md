# Windows App

`apps/windows/`는 FlowNote Windows WPF 클라이언트 영역이다. 현장/관리자 PC에 설치해 사용하는 네이티브 앱을 기준으로 한다.

## 현재 구현

- 로그인 화면과 메인 탐색기 화면
- 로컬 SQLite 초기화와 기본 계정/그룹/폴더 시드
- 사용자 관리: 사용자 추가, 이름/역할/비밀번호 변경
- 폴더 트리와 문서 목록
- 새 폴더 생성
- 샘플 문서 등록, 파일 업로드, Drag & Drop 등록
- 문서 상태 변경과 공개 버전 지정
- 문서 태그 저장과 표시
- TXT, PDF, XLSX, 이미지 미리보기
- 문서 열람 시작/종료 로그
- viewer 자동 닫힘과 다운로드 차단 로그
- FieldComment 작성과 첨부 저장
- 알림, 전체 이력
- 관리자 파일 감시 후보 처리
- 작업순서 관리자 화면과 TV 화면
- 보고서 초안 생성 보조, 문서 저장, 서버 보고서 저장 시도
- FastAPI 서버 인증과 문서/FieldComment/첨부/접근 로그/보고서/작업순서 API 클라이언트
- 서버 동기화 큐: 문서, FieldComment, FieldComment 첨부, 문서 접근 로그

## 프로젝트 구조

```text
apps/windows/
  docs/                         Windows 앱 구현 문서
  src/FlowNote.Windows.App/     WPF UI
  src/FlowNote.Windows.Core/    로컬 DB, 서비스, 정책, 서버 API 클라이언트
  src/FlowNote.Windows.SmokeTests/  콘솔 스모크 테스트
```

## 로컬 데이터

기본 DB 경로는 저장소 루트의 `data/local/flownote.local.sqlite`이다.

- `FLOWNOTE_LOCAL_DATA_DIR`: 로컬 데이터 폴더 override
- `FLOWNOTE_LOCAL_DATABASE_PATH`: SQLite 파일 경로 override
- `FLOWNOTE_API_BASE_URL`: FastAPI 서버 URL
- `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS`: 뷰어 자동 닫힘 시간

업로드 파일과 FieldComment 첨부는 로컬 데이터 폴더의 `Files/` 아래 보존한다.

## 권한 요약

- 문서 등록/작업순서 편집: 관리자 계열, 반장, 조장
- 보고서 작성: 관리자/문서관리/부서관리 계열
- 파일 감시: 관리자 계열만
- 사용자 관리: `admin`, `system-admin`
- 다운로드 허용: 관리자 계열 중 `admin`, `system-admin`, `manager`, `document-admin`, `assistant-manager`, `department-manager`
- FieldComment 작성: 모든 기본 현장 role

서버 URL이 설정된 상태에서 서버가 401 또는 403으로 로그인 실패를 응답하면 로컬 계정으로 우회하지 않는다. 서버 URL이 없거나 서버에 연결할 수 없는 경우에만 로컬 계정 로그인을 사용한다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

스모크 테스트는 공통 SQLite에 기록을 누적한다. 테스트 DB와 파일 산출물은 사용자가 명시적으로 삭제를 지시하지 않는 한 보존한다.

파일 유형별 미리보기 샘플과 실패 안내 기준은 [문서 미리보기 안정화 기준](./docs/document-preview-stability.md)을 따른다.
