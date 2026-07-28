# 2026-06-26 현재 작업 요약

이 문서는 2026-06-26 기준 작업 내용을 현재 코드 기준으로 정리한 기록이다.

## 구현된 Windows 앱 범위

- 로그인과 권한 기반 화면 접근
- 사용자 목록, 사용자 생성, 역할 변경, 비밀번호 변경
- 문서 폴더, 문서 등록, 문서 목록/상세, 문서 버전
- 문서 열람 이력과 다운로드 권한 제어
- 서버 공개 버전 controlled copy 저장과 SHA-256 검증
- FieldComment 등록, 조회, 첨부, 원천 불변, 단계형 검토·일괄 처리·품질 작업함
- 작업순서 보드, 항목, 상태 변경, 이력, 알림 후보. 로컬 row는 캐시·초안이고 서버 snapshot·`board_revision`·mutation receipt가 최종 권위다.
- 알림 목록
- 채널함, 채널 관리, 인수인계 확인 현황
- 보고서 초안 보조와 보고서 저장
- AI 근거 후보 운영 점검 화면
- `AI 정답셋` 사례·원천 구성, dataset version 운영, 실제 익명 현장 24칸 독립 표본 검토와 불일치 제3 합의 화면
- `system-admin` 전용 외부 AI 운영 제어 화면
- 승인 단말 관리 화면
- 서버 계정 수명주기와 강제 비밀번호 변경 화면
- 서버 scope·사용자별 알림 cursor 보존, instance/epoch 복구 경계·관리자 재결합과 보존 FAILED 큐 전환 CLI
- 서버 동기화 큐와 서버 ID 매핑 테이블

## 구현된 서버 범위

- 인증과 세션 관리
- 승인 단말 관리와 Android 단말 로그인 검증
- 문서, 버전, 태그, 공개 버전
- FieldComment와 첨부, 원천 불변·검토 revision·mutation receipt·감사·품질 API
- 문서 열람 로그
- 작업순서와 알림 후보, 보드 revision·mutation receipt
- 채널/인수인계
- 보고서 revision·내용/source 집합 hash·mutation receipt와 고정 근거 재검증
- AI 검색 전 단계의 근거 후보 재생성·목록·품질, 독립 승인 사례와 불변 dataset version 기반 회귀 평가, 실제 익명 현장 24칸 독립 표본 검토·제3 합의 API, 외부 AI 질의의 기본 비활성 안전장치·응답 검증·감사 골격
- 서버 계정 수명주기, 승인 단말 세션 폐기와 고객·현장별 AI 민감정보 정책 필터
- `system-admin` 전용 외부 AI 승인·프롬프트·운영 정책·provider 착수 심사·감사·보존 API
- 서버 instance/epoch/API contract manifest와 WPF 큐 inventory reconciliation·관리자 승인 적용 API

## 현재 판단 기준

이 문서는 과거 작업 요약이다. 현재 기능 판단은 코드와 `docs/`의 최신 설계 문서를 기준으로 한다.
