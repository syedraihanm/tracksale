Unicode true
RequestExecutionLevel user
SetCompressor /SOLID zlib

!include "MUI2.nsh"

!define APP_NAME "AMEE MOBILES POS"
!define APP_VERSION "0.1.0"
!define APP_EXE "Amee Mobiles POS.exe"
!define APP_KEY "Software\AMEE MOBILES POS"
!define MUI_ICON "..\app\static\app.ico"
!define MUI_UNICON "..\app\static\app.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch AMEE MOBILES POS"

Name "${APP_NAME}"
Caption "${APP_NAME} Setup"
OutFile "..\dist\AmeeMobilesSetup.exe"
InstallDir "$LOCALAPPDATA\Programs\Amee Mobiles POS"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
ShowInstDetails show
ShowUnInstDetails show
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright (c) 2026 AMEE MOBILES"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\Amee Mobiles POS\*.*"

  WriteRegStr HKCU "${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AmeeMobilesPOS" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AmeeMobilesPOS" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AmeeMobilesPOS" "DisplayVersion" "${APP_VERSION}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\Amee Mobiles POS"
  CreateShortcut "$SMPROGRAMS\Amee Mobiles POS\Amee Mobiles POS.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut "$DESKTOP\Amee Mobiles POS.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut "$SMSTARTUP\AmeeMobilesServer.lnk" "$INSTDIR\${APP_EXE}" "--background" "$INSTDIR\${APP_EXE}" 0
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\Amee Mobiles POS.lnk"
  Delete "$SMPROGRAMS\Amee Mobiles POS\Amee Mobiles POS.lnk"
  Delete "$SMSTARTUP\AmeeMobilesServer.lnk"
  RMDir "$SMPROGRAMS\Amee Mobiles POS"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AmeeMobilesPOS"
  DeleteRegKey HKCU "${APP_KEY}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
  ; Shop database, backups, logs, and secrets are in %LOCALAPPDATA%\AmeeMobiles and are preserved.
SectionEnd
