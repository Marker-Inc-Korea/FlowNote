@echo off
set APP_HOME=%~dp0
set GRADLE_VERSION=8.10.2
set GRADLE_USER_HOME=%APP_HOME%\.gradle
set DIST_DIR=%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin\gradle-%GRADLE_VERSION%
set DIST_ZIP=%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin\gradle-%GRADLE_VERSION%-bin.zip
set DIST_URL=https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip

if not exist "%DIST_DIR%\bin\gradle.bat" (
  mkdir "%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin" 2>nul
  if not exist "%DIST_ZIP%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%DIST_URL%' -OutFile '%DIST_ZIP%'"
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force '%DIST_ZIP%' '%GRADLE_USER_HOME%\wrapper\dists\gradle-%GRADLE_VERSION%-bin'"
)

call "%DIST_DIR%\bin\gradle.bat" %*
