# 0007. 웹 스택, MySQL, 고객 데이터 주권 기반 배포

## 상태

Superseded by [0019. Python 백엔드와 Android/Windows 앱 중심 전환](./0019-python-backend-native-app-direction.md)

## 과거 결정 요약

이 문서는 과거에 TypeScript, React, Vite 기반 Web UI를 기준 스택으로 두려던 결정을 기록한 ADR이다.

## 유지되는 결정

- 이 결정에서의 MySQL 기본값은 폐기되었고, 0020에 따라 SQLite 우선, 필요 시 PostgreSQL로 대체한다.
- 파일 바이너리는 MySQL에 직접 저장하지 않고 파일 저장소에 둔다.
- 배포 설계는 고객 또는 현장별 독립 인스턴스를 기본으로 한다.
- 실제 설치 위치와 외부 접근 허용 여부는 고객 보안 정책과 협의해 결정한다.
- 내부망 전용 운영과 인가된 외부 접근 운영을 모두 고려한다.

## 대체 결정

Web UI 스택 결정은 폐기한다. 백엔드는 Python FastAPI 서버로 전환하고, 프론트엔드는 WPF 또는 Avalonia 클라이언트로 구현한다.
