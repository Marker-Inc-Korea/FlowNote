# 탐색기형 셸 화면

## 목적

현장 사용자가 처음 체감할 FlowNote 클라이언트 화면은 윈도우 탐색기처럼 문서를 찾고 상태를 확인하는 화면이다. 현재 WPF 구현은 이 흐름을 검증하기 위한 초기 셸이다.

## 현재 화면 구조

- 상단 작업 막대: FlowNote 앱명, 새 폴더, 문서 등록 버튼 자리
- 좌측 탐색 영역: 루트와 기본 폴더를 표시하는 폴더 트리
- 중앙 작업 영역: 검색 입력과 문서 목록
- 우측 상세 영역: 선택 문서의 상태, 버전, 현장 기록 요약 자리
- 하단 상태 영역: 클라이언트 상태 메시지 자리

## 좌측 트리 기본 폴더

초기 실행 시 로컬 SQLite에 루트 폴더 `Root`를 만들고, 그 아래에 다음 네 개 기본 폴더를 만든다.

- `문서`
- `인수인계`
- `작업순서`
- `사진`

이 네 개 폴더는 시스템 폴더로 처리한다. 사용자는 기본 폴더를 삭제할 수 없고, 기존 로컬 DB에 같은 이름의 폴더가 있으면 초기화 과정에서 시스템 폴더로 보정한다.

## 현재 코드 위치

- WPF 앱 프로젝트: `apps/windows/src/FlowNote.Windows.App/`
- 코어 모델 프로젝트: `apps/windows/src/FlowNote.Windows.Core/`
- 화면 XAML: `apps/windows/src/FlowNote.Windows.App/MainWindow.xaml`
- 화면 바인딩 모델: `apps/windows/src/FlowNote.Windows.Core/Explorer/`

## 현재 범위

포함된 것:

- WPF 앱 프로젝트 생성
- 코어 프로젝트 생성
- 탐색기형 레이아웃 구성
- 로컬 SQLite 폴더와 문서 목록 바인딩
- 루트 아래 기본 폴더 4개 자동 생성
- 기본 폴더 삭제 차단
- 문서 상세 패널 자리 구성
- 로그인 성공 후 탐색기 화면 표시

포함하지 않은 것:

- FastAPI 서버 연동
- 실제 파일 업로드
- 파일 감시
- 다운로드 차단
- 문서 뷰어 자동 닫힘

## 검증

빌드 명령:

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```

결과:

- 경고 0개
- 오류 0개
- 스모크 테스트 통과
