# 로컬 SQLite 기본 구조

## 목적

Windows WPF 클라이언트가 서버 연동 전에도 로그인, 폴더 관리, 문서 등록의 기본 흐름을 검증할 수 있도록 로컬 SQLite 저장소를 둔다.

이 저장소는 최종 서버 데이터베이스를 대체하지 않는다. 현재 단계에서는 클라이언트 화면 흐름과 기본 서비스 경계를 확인하기 위한 로컬 구조이다.

## 기본 설정

- DB 경로: `%LOCALAPPDATA%\FlowNote\flownote.local.sqlite`
- 기본 로그인 ID: `admin`
- 기본 비밀번호: `1234`
- 기본 역할: `system-admin`
- 앱 시작 방식: 로그인 창이 먼저 열리고, 로그인 성공 후에만 탐색기 화면을 사용할 수 있다.
- 기본 루트 폴더: `Root`
- 루트 아래 기본 폴더: `문서`, `인수인계`, `작업순서`, `사진`

## 테이블

현재 로컬 DB는 다음 테이블을 만든다.

- `user_accounts`: 로그인 계정
- `document_folders`: 문서 폴더
- `documents`: 문서 등록 기본 정보

## 서비스 위치

- `FlowNoteLocalDatabase`: SQLite 파일 생성, 스키마 생성, 기본 데이터 시드
- `FlowNoteLocalServices`: Auth, Folders, Documents 서비스 묶음
- `AuthService`: 로그인 검증
- `FolderService`: 폴더 생성, 목록, 삭제
- `DocumentService`: 문서 등록, 목록
- `DocumentPlacementService`: 기본 폴더별 문서 배치와 제목 생성 규칙

## 현재 동작

- 기본 계정 `admin / 1234`를 자동 생성한다.
- 기본 루트 폴더 `Root`를 자동 생성한다.
- 루트 아래에 `문서`, `인수인계`, `작업순서`, `사진` 폴더를 자동 생성한다.
- 네 개 기본 폴더는 시스템 폴더로 표시하며 삭제할 수 없다.
- 기존 로컬 DB에 같은 이름의 기본 폴더가 있으면 초기화 과정에서 시스템 폴더로 보정한다.
- 새 폴더 버튼은 루트 아래에 폴더를 만든다.
- 문서 등록 버튼은 기본 폴더 `문서`에 샘플 문서 메타데이터를 등록한다.
- `인수인계` 폴더에 파일을 등록하면 `yyyy-MM-dd` 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- `작업순서` 폴더에 파일을 등록하면 파일명에서 확장자를 제외한 값을 작업 제목으로 자동 생성한다.
- `사진` 폴더에 파일을 등록하면 `yyyy-MM-dd` 날짜 하위 폴더를 만들고 그 아래에 배치한다.
- 문서가 들어 있는 폴더와 시스템 폴더는 삭제하지 않는다.

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

검증 내용:

- `admin / 1234` 로그인 성공
- 잘못된 비밀번호 로그인 실패
- 루트 폴더 자동 생성
- 기본 폴더 4개 자동 생성
- 기본 폴더 삭제 차단
- 폴더 생성 후 목록 조회
- 문서 등록 후 목록 조회
- `인수인계` 파일 등록 시 날짜 하위 폴더 생성
- `사진` 파일 등록 시 날짜 하위 폴더 생성
- `작업순서` 파일 등록 시 파일명 기반 작업 제목 생성
- 업로드 후보 파일명과 파일 크기 생성
- 업로드 후보가 파일 목록에 추가되는지 확인
- 문서가 있는 폴더 삭제 차단
