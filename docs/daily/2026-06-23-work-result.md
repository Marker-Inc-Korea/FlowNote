# 2026-06-23 작업 결과

이 문서는 2026-06-23 작업 결과를 현재 코드 기준으로 정리한 기록이다.

## 완료된 정리

- 제품 방향을 단순 DMS나 순수 KMS가 아니라 문서와 현장 지식을 함께 축적하는 구조로 정리했다.
- 서버는 FastAPI, 클라이언트는 Windows WPF, DB는 SQLite 우선이라는 개발 기준을 세웠다.
- 배포 기준은 서버 PC 1대와 Windows 설치형 클라이언트 배포로 정리했다.
- MES/ERP는 대체 대상이 아니라 후속 연동 대상이라는 범위를 명확히 했다.

## 현재 코드 반영 상태

- 서버 API는 `/api/v1` 경로 아래 인증, 승인 단말, 문서와 controlled copy, FieldComment, 태그, 작업순서, 채널/인수인계, 보고서, AI 근거 후보·회귀 평가와 외부 AI 질의 안전장치 기능을 구현한다.
- Windows 앱은 공통 로컬 SQLite `data/local/flownote.local.sqlite`를 사용하며, 환경 변수로 위치를 바꿀 수 있다.
- 현장 기록 명칭은 코드, DB, API, 문서에서 `FieldComment` / `field_comments` / `field-comments`를 사용한다.

## 남은 후속 범위

- 운영 provider를 통한 실제 외부 AI 검색·요약과 조언
- MES/ERP 자동 연동
- 외부 접근이나 클라우드 운영
- Android 운영 배포 서명·MDM·인증서와 추가 클라이언트 플랫폼

현재 서버에는 외부 AI 호출 없이 DB 원천에서 재생성하는 `ai_search_candidates` 근거 후보 재생성·목록·품질·오프라인 회귀 평가와 `/api/v1/ai/queries` 기본 비활성 안전장치·감사 골격이 구현되어 있고, WPF에는 근거 후보 운영 점검 화면이 있다. 운영 provider 네트워크 client는 없다.
