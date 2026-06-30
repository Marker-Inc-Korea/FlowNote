# 2026-06-24 API SQLite MVP 기록

이 문서는 FastAPI 서버의 SQLite MVP 작업 기록을 현재 코드 기준으로 정리한 것이다.

## 현재 서버 기준

- FastAPI 앱은 `/api/v1` 아래에 인증, 문서, FieldComment, 태그, 작업순서, 보고서 라우터를 제공한다.
- 기본 DB URL은 `sqlite:///./data/flownote.sqlite3`이다.
- 테스트 DB 기본값은 `sqlite:///./data/flownote.test.sqlite3`이다.
- 파일 저장소 기본값은 `./storage`이다.
- 개발 기본 관리자 계정은 DB가 비어 있을 때 시드된다.

## 스키마 범위

- 사용자와 세션: `users`, `auth_sessions`
- 문서와 버전: `documents`, `document_versions`
- 태그: `tags`, `document_tags`
- 현장 코멘트: `field_comments`, `field_comment_attachments`
- 열람 이력: `document_access_logs`
- 작업순서: `work_sequence_boards`, `work_sequence_items`, `work_sequence_change_history`, `work_sequence_notification_candidates`
- 보고서: `reports`
- 마이그레이션 기록: `schema_migrations`

## 구현된 주요 흐름

- 로그인 후 Access Token과 Refresh Token을 발급한다.
- Refresh Token 사용 시 토큰을 회전하고 이전 토큰 재사용을 거부한다.
- 문서 등록 시 파일을 서버 로컬 저장소에 저장하고 SHA-256, 크기, MIME/확장자를 기록한다.
- 새 문서 버전 등록 시 이전 최신 버전은 `SUPERSEDED`로 바뀐다.
- 공개 문서는 명시적으로 공개 버전을 지정해야 조회할 수 있다.
