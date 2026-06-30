# 탐색기형 셸 화면

## 목적

Windows WPF 앱의 첫 화면은 현장과 관리자가 익숙한 탐색기형 구조에서 문서를 찾고 등록하며, 현재 문서의 코멘트와 이력을 확인하는 화면이다.

## 현재 화면 구조

- 시작 화면: 로그인 창. 서버 URL이 있으면 FastAPI 로그인을 먼저 시도하고 실패 시 로컬 SQLite 로그인으로 폴백한다.
- 상단 작업 영역: 알림함, 이력, 새 폴더, 문서 등록, 파일 업로드, 작업순서판 관련 버튼
- 좌측 영역: 문서 폴더 트리
- 우측 영역: 검색 입력, 문서 목록, Drag & Drop 업로드 영역
- 하단 영역: 현재 작업 상태와 서버 동기화 결과 메시지

문서 등록 권한이 없는 role은 문서 등록, 파일 업로드, Drag & Drop 업로드, 작업순서판 편집 기능을 사용할 수 없다. 현재 문서 등록 가능 role은 관리자 계열, 반장, 조장이다.

## 기본 폴더

초기 실행 시 로컬 SQLite에 루트 폴더 `Root`와 아래 시스템 폴더를 보장한다.

- `문서`
- `인수인계`
- `작업순서`
- `사진`

`문서` 아래에는 작업 문서를 찾기 쉽게 다음 분류 폴더를 자동 생성한다.

- `도면`
- `작업표준서`
- `점검표`
- `품질검사`
- `안전수칙`
- `보전작업`
- `일반문서`

시스템 폴더는 삭제할 수 없다. 기존 DB에 같은 이름의 폴더가 있으면 초기화 과정에서 시스템 폴더로 보정한다.

## 문서 등록과 보기

파일 업로드 버튼이나 Drag & Drop으로 선택한 파일은 공통 로컬 데이터 폴더의 `Files\Uploads\yyyy-MM-dd\` 아래로 복사되고, SQLite의 `documents`와 `document_versions`에 원본 버전 `v1`로 저장된다.

폴더별 배치 규칙은 다음과 같다.

- `문서`: 파일명, 제목, 문서 유형을 기준으로 `문서` 하위 분류 폴더 중 하나에 자동 배치한다.
- `인수인계`: 오늘 날짜의 `yyyy-MM-dd` 하위 폴더를 만들고 그 아래에 저장한다.
- `사진`: 오늘 날짜의 `yyyy-MM-dd` 하위 폴더를 만들고 그 아래에 저장한다.
- `작업순서`: 파일명에서 확장자를 제외한 값을 작업 제목으로 사용한다. 운영용 작업순서판 데이터와는 별도이다.

문서 목록 더블클릭 시 별도 문서 보기 창을 연다. 현재 미리보기는 텍스트, PDF, Excel 첫 시트, 이미지 파일을 대상으로 한다. PDF는 WebView2 기반 PDF 뷰어를 우선 사용하고, 실패 시 PdfPig 텍스트 추출 fallback을 사용한다.

## FieldComment와 접근 로그

문서 보기 창에서 새 코멘트를 저장하면 문서 버전을 증가시키지 않고 `field_comments`에 원천 이력으로 저장한다. 선택한 사진/파일 첨부는 `field_comment_attachments`와 로컬 파일 경로에 저장한다.

문서 보기 창 열림과 닫힘은 `document_view_logs`에 기록한다. `FLOWNOTE_VIEWER_AUTO_CLOSE_SECONDS` 설정값 기준으로 자동 닫힘이 발생하면 닫힘 사유를 `auto_closed`로 기록한다. 관리자급 다운로드 role이 아닌 사용자의 저장 시도와 WebView2 PDF 다운로드/새 창 요청은 `download_blocked`로 기록한다.

서버 URL과 Bearer token이 있으면 문서, FieldComment, FieldComment 첨부, 접근 로그 전송 후보를 `server_sync_queue`에 남기고 즉시 재시도한다. 실패해도 로컬 저장은 성공으로 유지한다.

## 현재 포함하지 않는 범위

- 고도화된 파일 감시
- CAD 원본 직접 뷰어
- AI 검색/조언

## 검증

```powershell
dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj
dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj
```
