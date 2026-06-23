# 2026-06-23 작업 결과 정리

## 정리 목적

오늘 작업은 2026-06-19 이후 FlowNote 저장소를 연구과제용 기준으로 다시 정리한 흐름을 마무리하고, 실제 구현된 코드와 제품 문서의 기준을 맞추는 데 목적이 있다.

기존에 현장 실증과 파일럿 목적으로 만들었던 Z시리즈 성격의 작업물과, 연구과제 산출물로 관리할 FlowNote 저장소를 구분한다. 다만 FlowNote의 방향은 단순 데모가 아니라 실제 생산공장 현장에서 사용할 수 있는 문서 관리와 현장 지식 축적 구조를 목표로 유지한다.

## 오늘 반영한 결과

- Windows WPF 클라이언트 기준의 로컬 실행 구조를 정리했다.
- 로그인, 로컬 SQLite, 문서 폴더, 문서 등록, 파일 목록, Drag & Drop 등록, 문서 미리보기 흐름을 구현 기준으로 문서화했다.
- PDF 미리보기와 Excel 그리드 미리보기 흐름을 반영했다.
- 문서 버전, 현장 코멘트, 알림, 작업 이력, 감사 로그, 보고서 생성 보조가 장기적으로 연결되어야 한다는 제품 방향을 문서에 반영했다.
- FastAPI 서버는 현재 기본 상태 확인 API 중심의 초기 골격이며, 권한, 파일 저장, 문서 메타데이터, 감사 로그 API는 후속 구현 대상으로 분리했다.
- 기존 문서 중 현재 코드 기준과 맞지 않거나 중복되던 내용을 통합하고, `docs/product-overview.md`, `docs/system-map.md`, `docs/data-model.md`, `docs/api.md`, `docs/security.md`, `docs/decisions.md`의 역할을 다시 맞췄다.
- AI 검색과 작업 조언은 초기 핵심 기능이 아니라, 현장 문서 열람과 기록 데이터가 충분히 쌓인 뒤 활용할 후속 계층으로 정리했다.
- MES/ERP는 대체 대상이 아니라 후속 연동 대상이며, 초기 작업지시는 관리자 입력 기준으로 설계하는 방향을 명확히 했다.

## 검증 결과

- Windows WPF 앱 빌드: 통과
  - `dotnet build .\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj`
  - 경고 0개, 오류 0개
- Windows smoke test: 통과
  - `dotnet run --project .\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj`
  - `FlowNote Windows smoke tests passed.`
- FastAPI 정적 검사: 통과
  - `ruff check .`
  - `All checks passed!`
- FastAPI compile 확인: 통과
  - `python -m compileall app`
- FastAPI 기본 endpoint 확인: 통과
  - `/`: `200 {'service': 'FlowNote API', 'environment': 'local'}`
  - `/api/v1/health`: `200 {'status': 'ok'}`
- API pytest는 현재 실제 테스트 케이스가 없어 실행 대상이 없었다.
- API editable install은 flat layout package discovery 설정 문제로 보완이 필요하다.

## 마무리 판단

오늘 기준 저장소의 중심은 연구과제용 FlowNote로 정리한다. 단, 연구과제라는 이유로 실제 현장 사용성을 뒤로 미루지 않는다. 현장 사용자가 문서를 열람하고, 짧은 코멘트와 사진 기록을 남기며, 관리자가 이를 보고서와 이력으로 정제할 수 있는 흐름을 우선 검증해야 한다.

원문 메모의 개인적 판단과 배경 설명은 최종 산출물에 그대로 남기지 않고, 위와 같이 제품 방향과 작업 결과로 정리한다.

## 후속 작업

- FastAPI 문서/파일/권한/감사 로그 API 구현
- WPF 클라이언트와 서버 API 연동
- 다운로드 차단, 뷰어 자동 닫힘, 로컬 파일 제어 정책 구체화
- 문서 상태, 버전, 변경 사유, 코멘트 분석, 보고서 초안 생성 흐름 구현
- API packaging 설정 보완
- 실제 테스트 케이스 추가 및 테스트 산출물 보존 규칙 유지
