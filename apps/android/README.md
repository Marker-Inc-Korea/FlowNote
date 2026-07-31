# Android App

`apps/android/`는 FlowNote Android 현장 단말 클라이언트이다. 승인된 현장 태블릿 또는 러기드 단말에서 공개 문서 목록·상세와 PDF/이미지/TXT 앱 내부 보안 열람, FieldComment, 사진 기록, 신호등식 기록, 채널 알림 확인, 인수인계 작성·확인을 수행한다.

기능 목록은 2026-07-31 현재 `app/src/main` 코드 기준이며 운영 배포나 실단말에서만 확정할 항목은 별도 후속 범위로 표시한다.

## 기술 기준

- 언어/UI: Java, Android 네이티브 View
- Java 소스/타깃: 17
- 빌드: Gradle Android plugin, `./gradlew assembleDebug`
- 패키지: `com.flownote.fieldapp`
- SDK: `minSdk 26`, `targetSdk 35`, `compileSdk 35`
- 서버 통신: FastAPI `/api/v1` REST API, Bearer token, `HttpURLConnection`
- 로컬 임시 저장: Android SQLite `flownote_android_outbox.db`와 앱 전용 암호화 첨부 저장소

## 현재 화면 골격

- 화면 상단에 전송 대기 건수, 단말 보존 상태, 다음 자동 재시도 시점, 자동 재시도 한도와 승인 단말 ID를 계속 표시
- 서버 주소, 승인 단말 ID, 사용자 ID, 비밀번호 설정
- `deviceId` 포함 서버 로그인
- 공개 문서 목록과 문서 상세 메타데이터 조회. 상세 선택 시 문서/공개 버전 ID를 FieldComment 입력란에 연결
- 공개 버전의 PDF, PNG/JPEG/WebP, UTF-8 TXT 본문 보안 열람
- FieldComment 작성
- 사진 선택 상태 안내와 축소 미리보기, FieldComment 첨부 재전송. Android 10 이상은 시스템 thumbnail, Android 8~9는 메모리 제한 샘플링을 사용하고 기기 저장이 끝나면 선택 상태와 미리보기를 비움
- 신호등식 입력: `green`, `yellow`, `red`
- 채널 알림 조회와 읽음 처리
- 현재 사용자가 속한 활성 업무 채널과 활성 수신자를 고르는 인수인계 작성. 작업순서, 문서, FieldComment, 작업내역 원천 ID 중 하나가 필수
- 인수인계 조회와 `READ`, `ACKNOWLEDGED`, `FOLLOW_UP_REQUIRED` 확인

주요 버튼은 한 줄 안에서 같은 너비를 사용하고 최소 높이를 56dp로 둔다. 전송 상태와 일반 작업 상태는 접근성 live region으로 갱신한다. 이 값은 코드에 반영된 화면 기준이며 장갑 착용, 한 손 조작, 실제 거치 위치에서의 터치 성공률은 승인 실단말 관찰로 확정한다.

알림은 운영 로그인 동안 `specialUse` foreground service가 사내 HTTPS API를 기본 15초 간격으로 조회한다. 서버 주소와 사용자 조합을 hash한 scope별 cursor를 항목 표시 뒤 동기 저장하므로 앱 화면이 닫히거나 네트워크가 끊겨도 마지막 성공 위치에서 복구한다. 재부팅 시 유효한 로컬 세션이 있으면 `BOOT_COMPLETED` receiver가 서비스를 다시 시작하고, access 만료 시 refresh token을 한 번 회전한다. refresh가 거부되거나 단말이 비활성화되면 token을 폐기하고 서비스를 중단한다. 채널 메시지는 outbox에 넣지 않지만 신규 인수인계는 FieldComment·사진과 같은 암호화 outbox에 보존한다.

polling의 첫 401은 저장된 refresh token을 지우지 않고 회전을 먼저 시도한다. 회전 뒤에도 401이 반복되거나 단말 비활성화 403을 받았을 때만 세션을 폐기한다. 단순 HTTPS 단절·시간 초과는 세션과 cursor를 유지하고 다음 polling을 기다린다.

FieldComment, 사진과 신규 인수인계는 전송 전에 앱 전용 암호화 outbox에 먼저 저장한다. 앱 화면과 foreground service가 15초 주기로 전송 가능 항목을 재시도하므로 앱 재시작·재부팅·네트워크 재연결 뒤에도 같은 idempotency key로 이어서 보낸다. 마지막으로 서버가 확인한 활성 채널·수신자 목록은 서버 URL+사용자 범위별 Keystore 암호문으로 보관해 재부팅 직후 네트워크가 끊겨도 인수인계를 작성할 수 있게 한다. 서버는 실제 전송 시 멤버십과 원천을 다시 검사하며 로그아웃·단말 거부 때 선택 캐시는 지우고 업무 outbox는 유지한다. FieldComment 사진은 `android-photo:{localId}`, 인수인계는 `android:{deviceId}:handover:{localId}`를 사용한다. 서버가 FieldComment만 저장하고 사진 응답이 실패한 경우에는 서버 `comment_id`를 유지하고 부분 성공·사진 재전송 대기로 표시한다. 서버 저장이 끝난 암호화 사진 파일은 정리한다.

화면에는 전송 대기 건수, 보존 상태, 다음 자동 재시도 시점과 자동 재시도 한도 초과 여부를 계속 표시한다. 로그인 만료·refresh 거부·단말 비활성화 때도 outbox를 지우지 않으며, 다시 로그인하거나 관리자가 단말 상태를 확인할 때 사용할 승인 단말 ID와 대기 건수를 안내한다. Keystore를 열거나 암호문을 복호화하지 못하면 입력·전송을 차단하고 재설치·초기화 대신 단말 교체 점검을 안내한다. 사용자가 누르는 `재전송`은 자동 backoff와 시도 한도를 넘겨 대기 항목을 즉시 다시 시도한다.

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

네트워크 불안정 구간에서는 FieldComment, 사진 첨부와 신규 인수인계를 SQLite outbox에 임시 저장한다. access/refresh token, outbox JSON 본문과 마지막 오류 안내는 Android Keystore의 비반출 AES-256 GCM 키로 암호화한다. 새 사진은 선택 즉시 앱 전용 `filesDir/outbox-attachments/`로 복사하며 IV와 AES-GCM 암호문만 저장한다. 일반 SharedPreferences와 DB에는 token/원문 사진을 저장하지 않고 Android backup은 manifest에서 차단한다. DB 상태·서버 ID·멱등키·재시도 시각과 scope cursor는 업무 본문이 아니므로 평문 메타데이터로 유지한다.

재전송 정책:

- FieldComment는 `idempotencyKey = android:{deviceId}:{localId}`로 중복 생성을 방지한다.
- 사진 첨부는 `idempotencyKey = android-photo:{localId}`를 사용한다. FieldComment 서버 저장 후 사진 첨부가 실패하면 같은 outbox row에 서버 `comment_id`를 보존하고 다음 재전송에서 첨부만 다시 시도한다.
- 인수인계는 `idempotencyKey = android:{deviceId}:handover:{localId}`를 사용한다. 같은 키·같은 요청의 재전송은 기존 인수인계, 채널 메시지와 수신자 receipt를 반환하고 새 row를 만들지 않는다.
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

`scripts/verify-android-release.sh <run_id> <signed.apk|signed.aab> data/local/pilot-evidence`는 APK/AAB hash, signer SHA-256, applicationId, versionCode, non-debuggable, backup 비활성, cleartext 차단을 확인한다. AAB base manifest 검사는 PATH의 `bundletool` 또는 `BUNDLETOOL_JAR`가 필요하다. 설치 또는 rollback은 오배포를 막기 위해 `--device-serial <승인 adb serial>`을 반드시 함께 지정한다. `--rollback <previous.apk>`는 후보 APK를 먼저 설치하고, 후보 앱이 실제 단말에서 보고한 outbox 대기 0건을 원시 로그로 보존한 뒤에만 동일 signer와 더 낮은 versionCode인 이전 승인 APK를 설치한다. 대기 항목이 있거나 단말 보고를 읽을 수 없으면 rollback을 중단한다. AAB는 직접 설치·rollback할 수 없으므로 관리형 스토어가 실제 단말에 전달한 서명 APK를 별도로 검증해야 한다.

기존 원시 파일이 없으면 알림 복구 8건과 FieldComment·사진·인수인계의 실패→재시작→로그인→재전송, 멱등성, 비활성 단말, Keystore 실패, 대기 outbox rollback 차단을 합친 16건을 `android-delivery.csv`에 만든다. `android-field-ux.csv`에는 FieldComment·사진·인수인계 각각의 장갑·한 손·거치 조건 9건과 사진 선택·미리보기·저장 후 초기화 1건을 만든다. `full_pilot`은 이 10개 UX 행의 실제 성공, 서버 원천 ID, 치명적 blocker 0건과 같은 실행 폴더의 증거 파일을 모두 요구한다. 이 스크립트의 `result=PASS`는 패키지 정적 검사와 요청한 설치 단계만 뜻하며 수동 운영 시나리오는 별도 PASS가 필요하다. 실제 키와 운영 패키지는 Git 제외다.

`manage-pilot-run.py prepare --profile full_pilot`은 같은 실행 폴더에 `android-delivery.csv`, 누락·receipt 중복·crash 경계 중복 집계용 `android-delivery-integrity.csv`, `android-security.csv`, `android-device-lifecycle.csv`, `android-release-approval.csv`, `android-field-ux.csv`를 만든다. 요약 JSON만 PASS로 바꾸는 것으로는 통과하지 않으며, 각 원시 행이 `PASS`이고 행별 증거가 같은 `run_id` 폴더 안에 실제로 있어야 한다. MDM 제품명, 자산 ID, kiosk 재실행 제한 시간, rollout ring, 승인 번호와 이전 승인 package hash는 현장 승인값이므로 Git 문서에 가정값을 넣지 않고 접근 통제된 실행 증거에 기록한다.

## 제외 범위

- 개인 휴대폰 기본 배포
- GPS 추적
- 근태 관리
- 개인 메신저 수집
- 사내 메신저 전체 대체
- Office/HWP/CAD 등 PDF·이미지·TXT 이외 본문 렌더링

## 빌드와 테스트

```bash
cd apps/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
./gradlew lintDebug --warning-mode=fail
```

JDK와 Android SDK가 필요하다. macOS 기본 SDK 경로 `$HOME/Library/Android/sdk`가 있으면 `gradlew`가 `ANDROID_HOME`을 자동 지정한다. `JAVA_HOME`이 없고 기본 위치에 Android Studio가 있으면 내장 JDK도 자동으로 사용한다. 운영 배포 전에는 현장 서버 HTTPS, 사내 인증서, MDM 등록·정책 보고서와 단말별 `deviceId` 발급 절차를 확정해야 한다.

Windows 배포 준비 PC의 통합 기준선은 x64 JDK 17, Android Platform 35와 Build Tools 35.0.0을 사용한다. `scripts/verify-preserved-tests.ps1`은 단위 테스트와 debug build를 실행하고 JUnit XML과 단계 로그를 같은 실행 ID에 복사한 뒤 failure/error가 0인지 확인한다. 승인 실단말이 정확히 1대 연결된 경우에만 `-RunAndroidDeviceSmoke`를 추가한다. 이 자동 단계만으로 카메라 선택, 네트워크 단절 뒤 outbox 재시도, 사내 HTTPS 인증서 신뢰, foreground service/Doze/재부팅을 완료 판정하지 않으며 같은 실행 ID의 수동 실기 로그를 함께 남긴다.

2026-07-22 macOS 보조 run `p0-baseline-144-macos-precheck-20260722-002`은 FastAPI 144건만 통과했고 JDK/Android SDK 부재로 Android `testDebugUnitTest`와 `assembleDebug`는 `NOT_RUN`이다. 이 결과는 Android 기준선이 아니며 Windows x64 표준 환경의 같은 `run_id` 통합 실행에서 Android JUnit과 debug build가 통과해야 한다.

현재 단위 테스트 28건은 API 경로·로그인/FieldComment 계약, 인수인계 필수 원천·수신자·멱등키, Android view grant 경로와 SHA-256 계약, 사용자 오류 문구, outbox 재시도 정책과 대기 상태 안내, 알림 401 refresh·재거부·비활성 단말·연결 단절 분기를 검증한다. outbox 일부 실패는 완료·부분 성공·실패·대기 건수와 재전송 안내를 표시하고, Keystore/암호문 오류는 초기화하지 말고 관리자에게 단말 교체 점검을 요청하도록 안내한다. 계측 테스트는 보안 뷰어가 exported가 아닌지, `FLAG_SECURE`가 적용되는지, 내부 캐시 시작 정리, 서로 다른 AES 키의 복호화 실패, 주요 버튼 56dp와 상태 live region을 확인한다. 사진 선택·축소 미리보기·저장 후 초기화와 장갑·한 손 조건의 실제 성공률은 자동 테스트만으로 완료 판정하지 않는다. 실제 단말의 카메라·파일 선택기, 장갑·한 손 조작, 파일 앱·최근 항목·공유 메뉴·캐시 디렉터리·캡처 차단과 PDF/이미지/TXT·손상/대용량·네트워크 단절을 같은 수동 검증에서 확인한다.
