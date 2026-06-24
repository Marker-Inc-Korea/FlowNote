# 2026-06-24 문서 인코딩과 구현 상태 점검

## 1. 점검 목적

`docs/메모.txt`, `docs/decisions.md`처럼 깨져 보이는 문서가 실제 파일 손상인지, 콘솔 또는 도구의 문자 인코딩 표시 문제인지 확인했다. 함께 현재 코드 구현 상태와 문서에 적힌 목표 기능이 충돌하는지 점검했다.

## 2. 인코딩 점검 결과

현재 `docs/` 아래의 Markdown, TXT 문서는 모두 엄격한 UTF-8 디코딩을 통과했다. 대체 문자 `U+FFFD`도 발견되지 않았다.

점검 대상:

- `docs/README.md`
- `docs/api.md`
- `docs/data-model.md`
- `docs/decisions.md`
- `docs/deployment.md`
- `docs/implementation-roadmap.md`
- `docs/mvp-scope.md`
- `docs/product-overview.md`
- `docs/security.md`
- `docs/system-map.md`
- `docs/daily/2026-06-23.md`
- `docs/daily/2026-06-23-work-result.md`

`docs/decisions.md`는 실제 파일 내용이 UTF-8로 정상 저장되어 있다. 파일 시작 바이트도 `# FlowNote 설계 결정 요약`에 해당하는 정상 UTF-8 바이트이며, `Get-Content -Encoding UTF8`로 읽었을 때 한글이 정상 표시된다. 따라서 이 파일이 깨져 보인 경우는 파일 손상보다 콘솔 코드페이지, 터미널 폰트, Git 출력의 quoted path 표시, 또는 편집기 인코딩 자동 감지 문제로 판단한다.

## 3. 메모 파일 상태

현재 작업 트리와 Git 추적 파일 목록에는 `docs/메모.txt`가 없다. 전체 Git 이력에서도 `docs/메모.txt`라는 정확한 파일명은 찾지 못했다.

과거에는 아래 개인 메모성 TXT 파일이 존재했지만, `daf167f` 커밋에서 공식 문서로 통합되면서 삭제되었다.

- `docs/만들고자하는이유.txt`
- `docs/현장소리.txt`
- `docs/현장에서하는일.txt`

해당 과거 TXT 파일도 Git 이력에서 UTF-8로 정상 출력된다. 현재 기준에서는 원문 메모 파일을 다시 복구하기보다, 이미 정리된 공식 문서와 작업 결과 문서를 기준으로 유지하는 것이 맞다. 원문 메모의 개인적 배경 설명은 `docs/product-overview.md`, `docs/system-map.md`, `docs/decisions.md`, `docs/daily/2026-06-23-work-result.md`에 제품 방향과 작업 결과 형태로 통합되어 있다.

## 4. 현재 실제 구현 상태

현재 실제 동작하는 구현은 Windows WPF 로컬 SQLite 프로토타입이다.

구현됨:

- WPF 앱 로그인 선행 흐름
- 기본 계정 `admin / 1234`
- 테스트 계정 `jobhead / 반장 / 1234`가 포함된 로컬 SQLite 시드 DB
- 탐색기형 폴더 트리와 파일 목록
- 기본 시스템 폴더 `문서`, `인수인계`, `작업순서`, `사진`
- `문서` 하위 분류 폴더 `도면`, `작업표준서`, `점검표`, `품질검사`, `안전수칙`, `보전작업`, `일반문서`
- 기본 시스템 폴더 삭제 차단
- 새 폴더 생성
- 문서 등록 버튼 기반 샘플 문서 등록
- 파일 업로드 버튼과 Drag & Drop 파일 등록
- 업로드 파일을 앱 데이터 폴더의 `Data/Files/Uploads/yyyy-MM-dd/` 아래로 복사
- SQLite에 문서 메타데이터, 로컬 상대 경로, 원본 버전 `v1` 저장
- `문서` 루트 등록 시 파일명/제목 기반 분류 폴더 자동 배치
- `인수인계`, `사진` 폴더 등록 시 날짜 하위 폴더 자동 배치
- `작업순서` 폴더 등록 시 파일명 기반 제목 생성
- TXT, PDF, XLSX, 이미지 미리보기
- PDF는 WebView2 기반 표시, 실패 또는 텍스트 추출 필요 시 PdfPig 보조 사용
- XLSX는 첫 번째 시트를 표 형태로 표시
- 문서 보기 창의 누적 코멘트 표시
- 코멘트 저장 시 문서 버전 증가
- 코멘트 버전 생성 시 직전 버전 작성자에게 알림 생성
- 알림함과 읽음 처리
- Windows 앱 빌드 대상과 콘솔형 smoke test

FastAPI 서버는 아직 골격 단계이다.

구현됨:

- `GET /`
- `GET /api/v1/health`

## 5. 현재 미구현 상태

아래 항목은 문서에 제품 목표 또는 API 초안으로 존재하지만 현재 코드 구현 완료 기능이 아니다.

- FastAPI 인증 API
- FastAPI 문서 등록/조회/버전 API
- 서버 PC `storage/` 파일 저장소
- WPF 클라이언트와 FastAPI 서버 REST 연동
- 역할 기반 서버 권한
- 문서 상태 전환 UI와 서버 정책
- 다운로드 차단
- 뷰어 자동 닫힘
- 서버 감사 로그와 접근 로그
- 관리자 파일 감시
- 변경 후보 생성과 변경 사유 기반 새 버전 업로드 확정
- 태그 모델과 태그 검색
- 별도 `FieldNote` 현장 코멘트 모델
- 사진 첨부 기반 현장 기록 모델
- 작업자, 실제 전달자, 작업그룹 추적 모델
- 작업내역 모델
- 실제 운영용 작업순서판과 현장 TV 화면
- 보고서 생성과 관리자 검토 흐름
- AI 검색, 작업 조언, 보고서 초안
- MES/ERP 연동 어댑터
- HWP/DWG 고급 미리보기 또는 CAD-PDF 자동 변환
- 클라이언트 설치파일 배포 자동화

## 6. 문서 충돌 검토

현재 `docs/api.md`, `docs/data-model.md`, `docs/deployment.md`, `docs/implementation-roadmap.md`, `docs/mvp-scope.md`, `docs/security.md`, `docs/system-map.md`, `docs/decisions.md`에는 현재 구현과 미래 목표를 구분하는 문장이 들어가 있다. 따라서 서버 API, 보고서, AI, MES/ERP 항목은 현재 코드와의 충돌이 아니라 후속 설계 목표로 해석한다.

다만 `docs/README.md`의 핵심 관계 요약과 `apps/windows/README.md`의 예상 책임 표현은 파일 감시와 서버 연동이 현재 구현처럼 읽힐 여지가 있어 함께 갱신했다.

갱신 내용:

- `docs/README.md`에 이번 점검 문서 링크를 추가했다.
- `docs/README.md`의 로컬 기능 설명을 현재 구현된 로컬 파일 선택/미리보기와 후속 파일 감시로 분리했다.
- `apps/windows/README.md`에서 예상 책임을 목표 책임으로 바꾸고, 파일 감시와 서버 연동은 후속 구현임을 명시했다.

## 7. 결론

현재 확인된 범위에서는 `docs/` 문서의 실제 인코딩 손상은 없다. 깨져 보이는 현상은 콘솔 출력, Git quoted path 표시, 편집기 인코딩 감지 문제로 보는 것이 타당하다.

현재 구현 기준은 Windows WPF 로컬 SQLite 프로토타입과 FastAPI 헬스체크 골격이다. 문서에 있는 서버 API, 보안 정책, 보고서, AI, MES/ERP 연동은 제품 목표와 후속 구현 기준이며, 구현 완료 기능으로 해석하지 않는다.
