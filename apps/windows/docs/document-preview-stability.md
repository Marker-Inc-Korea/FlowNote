# 문서 미리보기 안정화 기준

이 문서는 WPF 문서 뷰어의 실제 현장 파일 유형별 미리보기 기준이다. 다운로드 차단, 자동 닫힘, 열람 로그는 파일 유형과 무관하게 동일하게 남겨야 한다.

## 공통 로그 기준

- 문서 창을 열면 `document_view_logs`에 열람 시작 row를 만들고 `activity_history`에 `document.view_started`를 기록한다.
- 사용자가 창을 닫으면 같은 열람 row에 `closed_at`, `close_reason = window_closed`를 기록하고 `activity_history`에 `document.view_closed`를 기록한다.
- 자동 닫힘이면 `close_reason = auto_closed`를 기록한다.
- 다운로드 또는 WebView2 PDF 저장/외부 창 요청이 차단되면 `close_reason = download_blocked`인 별도 접근 로그와 `document.download_blocked` 이력을 남긴다.
- 미리보기 실패, 대용량 제한, CAD/HWP 고급 뷰어 제외는 앱을 종료하지 않고 한글 안내를 표시하며 `document.preview_failed` 이력에 사유를 남긴다.

## 파일 유형별 샘플 기준

| 유형 | 정상 | 비정상 | 한글 파일명 | 큰 파일 |
| --- | --- | --- | --- | --- |
| TXT | UTF-8/BOM 감지 텍스트, 128 KiB 이하 | 인코딩 오류, 접근 불가, 손상 파일 | `작업표준서-혼합공정.txt` | 128 KiB 초과 시 본문 대신 메타데이터 |
| PDF | PDF 파서 검증 통과 후 WebView2 표시 | PDF 파서가 열 수 없는 파일 | `도면-프레스A-금형배치.pdf` | 5 MiB 이상도 앱 종료 없이 표시 또는 한글 실패 안내 |
| XLSX | `sheet1.xml`이 있는 첫 번째 시트, 최대 100행 표시 | ZIP/XML 구조 손상 | `품질점검표-라인A.xlsx` | 5 MiB 이상 또는 행/열이 많은 파일도 최대 100행 표시 |
| 이미지 | jpg/png/bmp/gif/tif/webp 디코딩 성공 | 이미지 디코더 실패 | `사진-설비점검-라인A.jpg` | 5 MiB 이상 또는 고해상도도 앱 종료 없이 표시 또는 한글 실패 안내 |

## PDF/WebView2 보안 기준

- WebView2 PDF는 저장, 다른 이름 저장, 인쇄 도구를 숨긴다.
- 기본 컨텍스트 메뉴와 브라우저 단축키를 끈다.
- `DownloadStarting`은 항상 취소하고 다운로드 차단 이력을 남긴다.
- `NewWindowRequested`는 외부 창을 열지 않고 다운로드 차단 이력을 남긴다.
- PDF가 손상된 경우 WebView2로 이동하지 않고 한글 오류 안내와 실패 이력을 남긴다.

## 실패 안내 문구 기준

- TXT 대용량: "TXT 파일이 미리보기 기준보다 큽니다"와 파일 크기, 제한 크기를 함께 표시한다.
- PDF 손상: "PDF 미리보기를 생성할 수 없습니다"와 손상 또는 미지원 형식 가능성을 표시한다.
- XLSX 손상: "엑셀 미리보기를 생성할 수 없습니다"를 표시한다.
- 이미지 손상: "이미지 미리보기를 생성할 수 없습니다"와 손상 또는 미지원 형식 가능성을 표시한다.
- 미지원 파일: "현재 클라이언트에서 이 파일 형식은 본문 미리보기를 지원하지 않습니다"를 표시한다.

## CAD/HWP 제외 범위

CAD와 HWP 고급 뷰어는 현재 MVP 범위에서 제외한다. `.dwg`, `.dxf`, `.step`, `.stp`, `.iges`, `.igs`, `.hwp`, `.hwpx`는 원본 첨부, 문서 메타데이터, FieldComment, 열람 시작/종료/다운로드 차단/자동 닫힘 로그만 기준으로 한다.

## 검증

WPF 스모크 테스트는 다음을 검증한다.

- TXT/PDF/XLSX/이미지 각각에 정상, 비정상, 한글 파일명, 큰 파일 샘플 기준이 정의되어 있다.
- TXT/PDF/XLSX/이미지 대표 샘플을 등록한다.
- 각 유형별 열람 시작, 열람 종료, 다운로드 차단, 자동 닫힘 로그가 공통 SQLite에 남는다.
- 스모크 테스트 출력에 `Preview audit smoke` 줄로 파일 유형, 샘플 파일 경로, 로그 ID가 남는다.
