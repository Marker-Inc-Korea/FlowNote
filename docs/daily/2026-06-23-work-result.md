# 2026-06-23 작업 결과

이 문서는 2026-06-23 작업 결과를 현재 코드 기준으로 정리한 기록이다.

## 완료된 정리

- 제품 방향을 단순 DMS나 순수 KMS가 아니라 문서와 현장 지식을 함께 축적하는 구조로 정리했다.
- 서버는 FastAPI, 클라이언트는 Windows WPF, DB는 SQLite 우선이라는 개발 기준을 세웠다.
- 배포 기준은 서버 PC 1대와 Windows 설치형 클라이언트 배포로 정리했다.
- MES/ERP는 대체 대상이 아니라 후속 연동 대상이라는 범위를 명확히 했다.

## 현재 코드 반영 상태

- 서버 API는 `/api/v1` 경로 아래 인증, 문서, FieldComment, 태그, 작업순서, 보고서 기능을 구현한다.
- Windows 앱은 공통 로컬 SQLite `data/local/flownote.local.sqlite`를 사용하며, 환경 변수로 위치를 바꿀 수 있다.
- 현장 기록 명칭은 코드, DB, API, 문서에서 `FieldComment` / `field_comments` / `field-comments`를 사용한다.

## 남은 후속 범위

- AI 검색과 조언
- MES/ERP 자동 연동
- 외부 접근이나 클라우드 운영
- 다중 클라이언트 플랫폼
