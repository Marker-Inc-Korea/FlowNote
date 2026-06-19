# 0020. 사내 서버형 FastAPI와 WPF/Avalonia 클라이언트 전환

## 상태

Accepted

## 배경

현장 테스트와 초기 배포를 쉽게 하기 위해 FlowNote의 기술 방향을 사내 서버형으로 좁힌다. 클라우드나 Web UI 중심 구조보다 서버 PC 1대와 설치형 클라이언트 구조가 생산현장 테스트와 고객 설명에 더 적합하다.

## 결정

- 서버는 Python FastAPI로 구현한다.
- 클라이언트는 WPF 또는 Avalonia 기반 설치형 네이티브 앱으로 구현한다.
- 통신은 REST API를 사용한다.
- DB는 SQLite를 우선 사용한다.
- 현장 규모, 동시성, 고객 IT 정책상 필요가 확인되면 PostgreSQL로 확장한다.
- 문서 파일은 서버 PC의 로컬 `storage/` 폴더에 저장한다.
- 배포는 서버 PC 1대와 클라이언트 설치파일 배포를 기본으로 한다.
- 독립 Web UI는 개발하지 않는다.
- Android는 초기 개발 대상에서 제외하고, 필요해질 때 후속 선택지로 둔다.

## 영향

- `services/api`는 FastAPI + SQLite + local storage 기준으로 구현한다.
- `apps/client`를 활성 클라이언트 개발 위치로 둔다.
- 기존 Web/Node/Windows 코드는 `legacy-*` 영역에 보존한다.
- MySQL 기준 문서는 SQLite 우선, PostgreSQL 후속 확장 기준으로 바꾼다.
- 배포 문서는 사내 서버 PC와 클라이언트 설치파일 기준으로 해석한다.
