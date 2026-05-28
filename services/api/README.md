# API Service

FlowNote API 서버 영역이다.

## 예상 책임

- 문서 등록, 조회, 다운로드
- 문서 버전 관리와 변경 사유 기록
- 현장 단말기용 최신 문서 제공
- 관리자 파일 변경 감지 결과 수신
- 권한, 이력, 접근 로그 관리
- 현장 코멘트와 정형 문구 관리
- 작업내역과 보고서 관리
- AI 검색과 작업 조언 API 제공
- MySQL 기반 메타데이터 저장

API 초안은 [docs/api.md](../../docs/api.md)를 기준으로 한다.

## 로컬 개발

로컬 테스트 DB는 `flowNote`를 사용한다.

```bash
mysql -u root -e "SOURCE /Users/truds/Projects/Project/FlowNote/services/api/init.sql"
npm install
npm run dev
```

기본 접속 정보는 다음과 같다.

```text
DB: flowNote
User: flownote
Password: 1234
Socket: /tmp/mysql.sock
API: http://127.0.0.1:5184
Nginx: http://flownote.localhost:8080/api/v1
```

현재 구현된 API:

- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `GET /api/v1/document-explorer`
- `POST /api/v1/document-folders`
- `GET /api/v1/system-history`
- `GET /api/v1/users`
- `PATCH /api/v1/users/{userId}/role`
- `GET /api/v1/work-sequence/items`
- `POST /api/v1/work-sequence/items`
- `PATCH /api/v1/work-sequence/items/order`
- `PATCH /api/v1/work-sequence/items/{sequenceItemId}`

초기 개발용 계정:

- 최고관리자: `admin` / `1234`
- MES 사용자: `mes` / `1234`
- POP 사용자: `pop` / `1234`
- 일반 사용자: `user` / `1234`

이전 개발 계정 `field` / `1234`도 POP 사용자로 매핑된다.
