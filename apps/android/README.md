# Android App

`apps/android/`는 FlowNote Android 현장 단말 클라이언트이다. 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세 메타데이터 조회, FieldComment, 사진 기록, 신호등식 기록, 채널 알림 확인, 인수인계 확인을 수행한다. 현재 코드는 문서 파일 본문 다운로드나 미리보기를 제공하지 않는다.

기능 목록은 2026-07-14 현재 `app/src/main` 코드 기준이며, 운영 배포나 실단말에서만 확정할 항목은 별도 후속 범위로 표시한다.

## 기술 기준

- 언어/UI: Java, Android 네이티브 View
- 빌드: Gradle Android plugin, `./gradlew assembleDebug`
- 패키지: `com.flownote.fieldapp`
- SDK: `minSdk 26`, `targetSdk 35`, `compileSdk 35`
- 서버 통신: FastAPI `/api/v1` REST API, Bearer token, `HttpURLConnection`
- 로컬 임시 저장: Android SQLite `flownote_android_outbox.db`

## 현재 화면 골격

- 서버 주소, 승인 단말 ID, 사용자 ID, 비밀번호 설정
- `deviceId` 포함 서버 로그인
- 공개 문서 목록과 문서 상세 메타데이터 조회. 상세 선택 시 문서/공개 버전 ID를 FieldComment 입력란에 연결
- FieldComment 작성
- 사진 선택과 FieldComment 첨부 재전송
- 신호등식 입력: `green`, `yellow`, `red`
- 채널 알림 조회와 읽음 처리
- 인수인계 조회와 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 확인

알림은 Activity가 전경일 때 기본 15초 간격으로 조회하고 연결 실패 시 최대 120초까지 backoff한다. 마지막 cursor는 서버 주소와 사용자별로 `SharedPreferences`에 보존한다. Android는 채널 메시지나 인수인계를 outbox에 저장하지 않는다.

## 승인 단말 정책

Android 로그인은 `/api/v1/auth/login`에 `deviceId`를 함께 보낸다. 서버는 `terminal_devices.device_id`가 존재하고 `status = ACTIVE`인 경우에만 로그인 세션을 발급한다. 승인되지 않은 단말 또는 비활성 단말은 403으로 거부된다.

Android가 자동으로 개인 휴대폰을 등록하지 않는다. 단말 등록, 정보/상태 변경, 비활성화, 교체는 `admin`, `system-admin`이 Windows WPF의 `승인 단말` 화면과 FastAPI 승인 단말 관리 API를 통해 수행한다. 현장별 등록·비활성화 절차, MDM, 운영 인증서 적용은 후속 운영 확정 범위다.

## 오프라인 임시 저장

네트워크 불안정 구간에서는 FieldComment와 사진 첨부만 SQLite outbox에 임시 저장한다. 저장 항목은 `local_id`, `idempotency_key`, 원천 문서/버전 ID, `device_id`, 사진 URI, 서버 `comment_id`, 시도 횟수와 마지막 오류를 가진다.

재전송 정책:

- FieldComment는 `idempotencyKey = android:{deviceId}:{localId}`로 중복 생성을 방지한다.
- FieldComment 서버 저장 후 사진 첨부가 실패하면 같은 outbox row에 서버 `comment_id`를 보존하고 다음 재전송에서 첨부를 다시 시도한다.
- 자동 재시도는 최대 12회이며 15초부터 최대 15분까지 지수 backoff를 적용한다.
- 재전송 성공 후 서버 원천 ID를 row에 남기고 `SYNCED`로 전환한다.

## 제외 범위

- 개인 휴대폰 기본 배포
- GPS 추적
- 근태 관리
- 개인 메신저 수집
- 사내 메신저 전체 대체
- 문서 파일 본문 다운로드·미리보기
- 인수인계 신규 작성

## 빌드와 테스트

```bash
cd apps/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

JDK와 Android SDK가 필요하다. macOS 기본 SDK 경로 `$HOME/Library/Android/sdk`가 있으면 `gradlew`가 `ANDROID_HOME`을 자동 지정한다. 운영 배포 전에는 현장 서버 HTTPS, 사내 인증서, 단말별 `deviceId` 발급 절차를 확정해야 한다.

Windows 배포 준비 PC의 통합 기준선은 `scripts/verify-preserved-tests.ps1`이 단위 테스트와 debug build를 같은 실행 ID로 보존한다. 승인 실단말이 정확히 1대 연결된 경우에만 `-RunAndroidDeviceSmoke`를 추가한다. 이 자동 단계만으로 카메라 선택, 네트워크 단절 뒤 outbox 재시도, 사내 HTTPS 인증서 신뢰, 전경 polling을 완료 판정하지 않으며 같은 실행 ID의 수동 실기 로그를 함께 남긴다.

현재 단위 테스트는 API 경로·로그인/FieldComment payload 계약, 사용자 오류 문구와 outbox 재시도 횟수·지수 backoff 정책을 검증한다. 실제 단말의 사진 선택, SQLite 지속성, 사내망 통신과 승인 단말 로그인은 Android 실기 검증 대상이다.
