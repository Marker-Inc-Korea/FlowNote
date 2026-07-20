# Android App

`apps/android/`는 FlowNote Android 현장 단말 클라이언트이다. 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세와 PDF/이미지/TXT 앱 내부 보안 열람, FieldComment, 사진 기록, 신호등식 기록, 채널 알림 확인, 인수인계 확인을 수행한다.

기능 목록은 2026-07-20 현재 `app/src/main` 코드 기준이며, 운영 배포나 실단말에서만 확정할 항목은 별도 후속 범위로 표시한다.

## 기술 기준

- 언어/UI: Java, Android 네이티브 View
- 빌드: Gradle Android plugin, `./gradlew assembleDebug`
- 패키지: `com.flownote.fieldapp`
- SDK: `minSdk 26`, `targetSdk 35`, `compileSdk 35`
- 서버 통신: FastAPI `/api/v1` REST API, Bearer token, `HttpURLConnection`
- 로컬 임시 저장: Android SQLite `flownote_android_outbox.db`와 앱 전용 암호화 첨부 저장소

## 현재 화면 골격

- 서버 주소, 승인 단말 ID, 사용자 ID, 비밀번호 설정
- `deviceId` 포함 서버 로그인
- 공개 문서 목록과 문서 상세 메타데이터 조회. 상세 선택 시 문서/공개 버전 ID를 FieldComment 입력란에 연결
- 공개 버전의 PDF, PNG/JPEG/WebP, UTF-8 TXT 본문 보안 열람
- FieldComment 작성
- 사진 선택과 FieldComment 첨부 재전송
- 신호등식 입력: `green`, `yellow`, `red`
- 채널 알림 조회와 읽음 처리
- 인수인계 조회와 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 확인

알림은 운영 로그인 동안 `specialUse` foreground service가 사내 HTTPS API를 기본 15초 간격으로 조회한다. 서버 주소와 사용자 조합을 hash한 scope별 cursor를 항목 표시 뒤 동기 저장하므로 앱 화면이 닫히거나 네트워크가 끊겨도 마지막 성공 위치에서 복구한다. 재부팅 시 유효한 로컬 세션이 있으면 `BOOT_COMPLETED` receiver가 서비스를 다시 시작하고, access 만료 시 refresh token을 한 번 회전한다. refresh가 거부되면 token을 폐기하고 서비스를 중단한다. Android는 채널 메시지나 인수인계를 outbox에 저장하지 않는다.

목표는 정상 사내망·서비스 실행 상태에서 서버 생성 후 30초 이내 표시, 5분 이상 단절 복구 후 30초+전송 시간 이내 따라잡기다. 동일 `message_id`는 같은 시스템 알림 ID를 사용하고 cursor를 각 표시 뒤 확정하므로 프로세스가 정확히 그 경계에서 죽을 때 허용되는 시각 중복은 최대 1건이다. 서버 알림 읽음과 인수인계 receipt는 기존 공개 ID/receipt row에 대한 멱등 갱신이어서 중복 서버 receipt는 0건이어야 한다. Android 사용자가 앱을 강제 중지하면 OS가 receiver와 service 재시작을 막으므로 MDM kiosk 재실행 또는 사용자 명시 재실행 전까지 목표 시간을 보장하지 않는다.

service 실행마다 `ANDROID-DELIVERY-{uuid}` run ID를 만들고 Logcat에 서버 `created_at`, Android `displayed_at`, message ID를 남긴다. 앱의 읽음/receipt 요청도 현재 run ID를 보내 서버 `activity_history` 처리 시각과 같은 실행으로 비교할 수 있게 한다.

한 page는 100건이며 응답이 정확히 100건이면 같은 polling cycle에서 다음 page를 계속 받는다. 각 `page_ok` 로그는 `cursor_before`, `cursor_after`, `received`, `advanced`, `stale_or_duplicate`를 기록한다. 가득 찬 page에서 cursor가 전진하지 않으면 무한 반복하지 않고 연결 복구 실패로 남긴다. 최초 과거 알림 catch-up과 101건 이상 단절 backlog는 승인 실단말에서 마지막 message ID까지 별도로 검증한다.

## 승인 단말 정책

Android 로그인은 `/api/v1/auth/login`에 `deviceId`를 함께 보낸다. 서버는 `terminal_devices.device_id`가 존재하고 `status = ACTIVE`인 경우에만 로그인 세션을 발급한다. 승인되지 않은 단말 또는 비활성 단말은 403으로 거부된다.

Android가 자동으로 개인 휴대폰을 등록하지 않는다. 단말 등록, 정보/상태 변경, 비활성화, 교체는 `admin`, `system-admin`이 Windows WPF의 `승인 단말` 화면과 FastAPI 승인 단말 관리 API를 통해 수행한다. 서버는 모든 access 요청과 refresh에서 세션의 `deviceId`가 계속 `ACTIVE`인지 재검사한다. 상태 API의 `INACTIVE`/`RETIRED`와 교체는 활성 세션도 같은 transaction에서 폐기한다. 현장별 MDM 제품과 운영 인증서 실기 적용은 현장 승인 항목이다.

## 본문 보안 열람

문서 상세의 `본문 보안 열람`은 Android 전용 grant API를 사용한다. 승인된 활성 단말과 허용 role만 현재 `PUBLISHED` 버전을 열 수 있고, grant는 기본 60초 안에 한 번만 사용할 수 있다. 앱은 서버가 반환한 크기와 SHA-256, 스트림 헤더 SHA-256을 수신 결과와 대조한 뒤 표시한다. PDF는 실제 `PdfRenderer` 페이지 수를 서버 한도와 다시 비교한다.

본문은 외부 저장소나 다운로드 폴더에 쓰지 않고 `cacheDir/secure-document-viewer/`의 확장자 없는 난수 파일에만 잠시 둔다. 뷰어 Activity는 비공개·최근 항목 제외이며 `FLAG_SECURE`를 설정한다. 공유, 외부 앱 열기, 파일 제공 URI는 구현하지 않는다. 열람 종료, 자동 닫힘, 앱 비활성화, 오류, 로그아웃에서 파일을 제거하고 다음 앱 시작 때 잔존 캐시를 정리한다. 네트워크 중단이나 무결성 실패에는 부분 파일을 삭제하며 소비된 grant 대신 새 열람 요청이 필요하다.

## 오프라인 임시 저장

네트워크 불안정 구간에서는 FieldComment와 사진 첨부만 SQLite outbox에 임시 저장한다. access/refresh token과 outbox JSON 본문은 Android Keystore의 비반출 AES-256 GCM 키로 암호화한다. 새 사진은 선택 즉시 앱 전용 `filesDir/outbox-attachments/`로 복사하며 IV와 AES-GCM 암호문만 저장한다. 일반 SharedPreferences와 DB에는 token/원문 사진을 저장하지 않고 Android backup은 manifest에서 차단한다. DB 상태·서버 ID·재시도 시각과 scope cursor는 업무 본문이 아니므로 평문 메타데이터로 유지한다.

재전송 정책:

- FieldComment는 `idempotencyKey = android:{deviceId}:{localId}`로 중복 생성을 방지한다.
- FieldComment 서버 저장 후 사진 첨부가 실패하면 같은 outbox row에 서버 `comment_id`를 보존하고 다음 재전송에서 첨부를 다시 시도한다.
- 자동 재시도는 최대 12회이며 15초부터 최대 15분까지 지수 backoff를 적용한다.
- 재전송 성공 후 서버 원천 ID를 row에 남기고 `SYNCED`로 전환한다.
- 기존 평문 DB는 첫 DB open에서 본문을 같은 schema 안에서 암호화한다. 기존 persist URI 첨부는 전송 완료까지 호환하고 새 항목부터 암호화 파일만 사용한다. 이전 APK rollback 전에는 `PENDING`/`FAILED` outbox가 0건이어야 한다. 이전 앱은 암호화된 미전송 본문·새 첨부를 해석할 수 없다.
- Keystore 키가 소실·무효화되면 token과 outbox를 복호화하거나 새 단말로 복사하지 않는다. 단말을 `INACTIVE` 처리하고 MDM 격리 후 미전송 건의 서버 존재 여부와 idempotency key를 관리자가 확인하며, 승인된 보존/폐기 절차 후 새 `deviceId`로 재등록한다.

## 운영 서명과 사내 배포

기본 운영 산출물은 MDM 또는 사내 배포용 서명 APK다. AAB는 관리형 스토어를 실제로 선택하고 앱 서명 책임을 별도 승인할 때만 사용한다. `assembleRelease`는 아래 네 환경변수가 모두 없으면 실패하며 keystore·암호는 저장소나 Gradle 파일에 쓰지 않는다.

release manifest는 cleartext HTTP를 금지한다. debug build만 개발용 사내 HTTP 접속을 허용하므로 debug APK를 운영 MDM allowlist에 올리지 않는다.

```bash
export FLOWNOTE_ANDROID_KEYSTORE=/secure/path/flownote-release.jks
export FLOWNOTE_ANDROID_KEY_ALIAS=flownote
export FLOWNOTE_ANDROID_STORE_PASSWORD='보안 입력 경로에서 주입'
export FLOWNOTE_ANDROID_KEY_PASSWORD='보안 입력 경로에서 주입'
./gradlew assembleRelease
```

조직 소유 서명키는 최소 2인 승인으로 오프라인/HSM 또는 승인된 비밀 저장소에 보관한다. 같은 applicationId의 무중단 업그레이드는 같은 키가 필요하다. 키 유출은 기존 키로 서명한 빌드 중단, MDM 차단, 새 applicationId 또는 승인된 키 회전 기능을 통한 재배포가 필요한 보안 사고다. 키 분실은 기존 앱을 새 키로 업그레이드할 수 없으므로 단말별 outbox 처리 후 제거·재등록 절차를 따른다.

`scripts/verify-android-release.sh <run_id> <signed.apk> data/local/pilot-evidence [--install] [--rollback <previous.apk>]`는 정확히 한 대의 승인 단말만 연결된 조건에서 APK hash, 인증서 지문, package 정보, device idle 상태와 전달 로그를 보존하고 선택적으로 업그레이드/rollback을 실행한다. 실제 키와 운영 패키지는 Git 제외다.

## 제외 범위

- 개인 휴대폰 기본 배포
- GPS 추적
- 근태 관리
- 개인 메신저 수집
- 사내 메신저 전체 대체
- Office/HWP/CAD 등 PDF·이미지·TXT 이외 본문 렌더링
- 인수인계 신규 작성

## 빌드와 테스트

```bash
cd apps/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

JDK와 Android SDK가 필요하다. macOS 기본 SDK 경로 `$HOME/Library/Android/sdk`가 있으면 `gradlew`가 `ANDROID_HOME`을 자동 지정한다. 운영 배포 전에는 현장 서버 HTTPS, 사내 인증서, MDM 등록·정책 보고서와 단말별 `deviceId` 발급 절차를 확정해야 한다.

Windows 배포 준비 PC의 통합 기준선은 x64 JDK 17, Android Platform 35와 Build Tools 35.0.0을 사용한다. `scripts/verify-preserved-tests.ps1`은 단위 테스트와 debug build를 실행하고 JUnit XML과 단계 로그를 같은 실행 ID에 복사한 뒤 failure/error가 0인지 확인한다. 승인 실단말이 정확히 1대 연결된 경우에만 `-RunAndroidDeviceSmoke`를 추가한다. 이 자동 단계만으로 카메라 선택, 네트워크 단절 뒤 outbox 재시도, 사내 HTTPS 인증서 신뢰, foreground service/Doze/재부팅을 완료 판정하지 않으며 같은 실행 ID의 수동 실기 로그를 함께 남긴다.

현재 단위 테스트는 API 경로·로그인/FieldComment payload, Android view grant 경로와 SHA-256 계약, 사용자 오류 문구와 outbox 재시도 정책을 검증한다. 계측 테스트는 보안 뷰어가 exported가 아닌지, `FLAG_SECURE`가 적용되는지, 내부 캐시 시작 정리가 동작하는지 확인한다. 실제 단말의 파일 앱·최근 항목·공유 메뉴·캐시 디렉터리·캡처 차단과 PDF/이미지/TXT·손상/대용량·네트워크 단절은 승인 실단말 수동 검증 대상이다.
