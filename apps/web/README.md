# Web App

Web 앱은 FlowNote 클라이언트 UI의 기준 구현이다. 브라우저뿐 아니라 Android WebView와 Windows WebView2에서도 같은 UI를 사용한다.

## 기술 기준

- 언어: TypeScript
- UI 라이브러리: React
- 빌드 도구: Vite
- 실행 형태: SPA

## 예상 책임

- 문서 등록, 버전 업로드, 변경 사유 관리
- 문서 권한, 태그, 연결 대상 관리
- 현장 코멘트 검토와 정리
- 정형 문구 템플릿 관리
- 작업내역과 보고서 관리
- AI 검색, 작업 조언, 위험 요소 미리보기 확인

## 설계 기준

- 문서 열람, 검색, 코멘트, 관리자 콘솔 UI는 웹에서 우선 구현한다.
- Android와 Windows 앱은 이 웹 UI를 WebView로 표시한다.
- 로컬 제어가 필요한 기능은 브라우저 API에 의존하지 않고 앱 브릿지를 통해 호출한다.
