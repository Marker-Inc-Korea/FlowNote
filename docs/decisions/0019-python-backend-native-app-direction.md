# 0019. Python 백엔드와 Android/Windows 앱 중심 전환

## 상태

Superseded by [0020. 사내 서버형 FastAPI와 WPF/Avalonia 클라이언트 전환](./0020-internal-server-fastapi-native-client.md)

## 배경

기존 문서는 Web UI를 먼저 만들고 Android/Windows 앱에서 WebView로 재사용하는 방향을 전제로 했다. 하지만 새 개발 방향에서는 웹 프론트엔드를 개발하지 않고, 현장 운영에 직접 사용할 Android 앱 또는 Windows 앱을 프론트엔드로 둔다.

백엔드도 기존 Node.js 또는 웹 중심 구현 흔적이 아니라 Python 기반 API 서버로 다시 잡는다.

## 결정

- 백엔드는 Python 기반 API 서버로 진행한다.
- API 경로와 외부 계약은 `/api/v1` REST API를 기준으로 유지한다.
- 이 중간 결정의 DB/클라이언트 기준은 0020으로 대체한다.
- 독립 Web UI, React/Vite/TypeScript 기반 SPA, WebView 기반 공통 UI는 신규 개발하지 않는다.
- 0020에서는 WPF/Avalonia 클라이언트가 현장/관리자 기능을 담당한다.
- 일반 브라우저 직접 접근은 운영 기본값으로 두지 않는다.
- 로컬 파일 감시, 파일 선택, 뷰어 자동 닫힘, 다운로드 차단은 앱 네이티브 기능과 서버 감사 로그를 함께 사용해 처리한다.

## 대체 사유

이 결정은 Web UI를 제외하고 Python API와 앱 중심으로 전환한 중간 결정이다. 이후 개발 기준이 사내 서버 PC 1대, WPF/Avalonia 클라이언트, FastAPI, SQLite 우선, 서버 로컬 storage로 더 구체화되어 0020으로 대체한다.

## 영향

- `apps/web`은 신규 개발 대상이 아니다.
- `services/api`는 Python 전환 대상이다.
- 기존 Web 우선 ADR인 0006, 0007, 0009는 이 결정으로 대체한다.
- 문서의 MVP, 로드맵, 아키텍처, 보안, 배포 기준은 Python API 서버와 Android/Windows 앱 중심으로 해석한다.
- MES/ERP 보완 연동, 문서와 현장지식의 균형 원칙은 유지한다.
