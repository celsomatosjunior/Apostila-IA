; Instalador do Transcritor IA Local (NSIS 3, Modern UI 2) — mesmo método do Capture Pro.
; Os modelos de IA NÃO vão no instalador: são baixados no primeiro uso, com consentimento.
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ManifestDPIAware true
RequestExecutionLevel admin

!define APPNAME "Transcritor IA Local"
!define APPEXE "TranscritorIA.exe"
!define COMPANY "Celso Matos Junior"
!ifndef VERSION
  !define VERSION "2.0.0"
!endif
!ifndef DISTDIR
  !define DISTDIR "..\..\dist\TranscritorIA"
!endif
!ifndef OUTFILE
  !define OUTFILE "TranscritorIA-Setup-${VERSION}.exe"
!endif
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\TranscritorIA"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\Transcritor IA Local"
InstallDirRegKey HKLM "Software\TranscritorIA" "InstallDir"
BrandingText "${APPNAME} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1046 "ProductName" "${APPNAME}"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do ${APPNAME}"
VIAddVersionKey /LANG=1046 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1046 "CompanyName" "${COMPANY}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "${COMPANY}"

!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "LogicLib.nsh"

!define MUI_ICON "..\..\assets\icone.ico"
!define MUI_UNICON "..\..\assets\icone.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APPEXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o Transcritor IA Local agora"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "O Transcritor IA Local requer Windows 64 bits."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "O Transcritor IA Local requer Windows 10 ou Windows 11."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Section "Transcritor IA Local (obrigatório)" SecMain
  SectionIn RO
  SetShellVarContext all
  nsExec::Exec 'taskkill /IM ${APPEXE} /F'
  ; remove arquivos de uma versão anterior (modelos, configurações e trabalhos ficam em %LOCALAPPDATA%)
  RMDir /r "$INSTDIR\Lib"
  RMDir /r "$INSTDIR\DLLs"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\engines"
  SetOutPath "$INSTDIR"
  File /r "${DISTDIR}\*.*"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"

  CreateDirectory "$SMPROGRAMS\Transcritor IA Local"
  CreateShortcut "$SMPROGRAMS\Transcritor IA Local\Transcritor IA Local.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
  CreateShortcut "$SMPROGRAMS\Transcritor IA Local\Desinstalar.lnk" "$INSTDIR\Desinstalar.exe"

  WriteRegStr HKLM "Software\TranscritorIA" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "${COMPANY}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\${APPEXE}"
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1
SectionEnd

Section "Atalho na Área de Trabalho" SecDesktop
  SetShellVarContext all
  CreateShortcut "$DESKTOP\Transcritor IA Local.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Programa completo. O modelo de IA é baixado no primeiro uso, com sua autorização."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Cria um ícone na Área de Trabalho."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.onInit
  SetRegView 64
FunctionEnd

Section "Uninstall"
  SetShellVarContext all
  nsExec::Exec 'taskkill /IM ${APPEXE} /F'
  Delete "$DESKTOP\Transcritor IA Local.lnk"
  RMDir /r "$SMPROGRAMS\Transcritor IA Local"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "Software\TranscritorIA"
  ; transcrições, modelos baixados e configurações (%LOCALAPPDATA%\TranscritorIA) são preservados
SectionEnd
