; Instalador do ApostilaIA (NSIS 3, Modern UI 2) — mesmo método do Capture Pro e do TranscritorIA.
; Os modelos de IA (vários GB) NÃO vão no instalador: são baixados no primeiro uso, com consentimento.
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ManifestDPIAware true
RequestExecutionLevel admin

!define APPNAME "ApostilaIA"
!define APPEXE "ApostilaIA.exe"
!define COMPANY "Celso Matos Junior"
!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef DISTDIR
  !define DISTDIR "..\..\dist\ApostilaIA"
!endif
!ifndef OUTFILE
  !define OUTFILE "ApostilaIA-Setup-${VERSION}.exe"
!endif
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ApostilaIA"

Name "${APPNAME}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\ApostilaIA"
InstallDirRegKey HKLM "Software\ApostilaIA" "InstallDir"
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
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o ApostilaIA agora"

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
    MessageBox MB_ICONSTOP "O ApostilaIA requer Windows 64 bits."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "O ApostilaIA requer Windows 10 ou Windows 11."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Section "ApostilaIA (obrigatório)" SecMain
  SectionIn RO
  SetShellVarContext all
  nsExec::Exec 'taskkill /IM ${APPEXE} /F'
  nsExec::Exec 'taskkill /IM llama-server.exe /F'
  ; remove arquivos de uma versão anterior (modelos, configurações e trabalhos ficam em %LOCALAPPDATA%)
  RMDir /r "$INSTDIR\Lib"
  RMDir /r "$INSTDIR\DLLs"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\llama"
  SetOutPath "$INSTDIR"
  File /r "${DISTDIR}\*.*"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"

  CreateDirectory "$SMPROGRAMS\ApostilaIA"
  CreateShortcut "$SMPROGRAMS\ApostilaIA\ApostilaIA.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
  CreateShortcut "$SMPROGRAMS\ApostilaIA\Desinstalar.lnk" "$INSTDIR\Desinstalar.exe"

  WriteRegStr HKLM "Software\ApostilaIA" "InstallDir" "$INSTDIR"
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
  CreateShortcut "$DESKTOP\ApostilaIA.lnk" "$INSTDIR\${APPEXE}" "" "$INSTDIR\${APPEXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Programa completo (interface, leitura de PDF, composição de PDF/DOCX e llama.cpp com Vulkan/CPU). Os modelos de IA são baixados no primeiro uso, com sua autorização."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Cria um ícone na Área de Trabalho."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.onInit
  SetRegView 64
FunctionEnd

Section "Uninstall"
  SetShellVarContext all
  nsExec::Exec 'taskkill /IM ${APPEXE} /F'
  nsExec::Exec 'taskkill /IM llama-server.exe /F'
  Delete "$DESKTOP\ApostilaIA.lnk"
  RMDir /r "$SMPROGRAMS\ApostilaIA"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${UNINSTKEY}"
  DeleteRegKey HKLM "Software\ApostilaIA"
  ; modelos baixados, projetos e configurações (%LOCALAPPDATA%\ApostilaIA) são preservados;
  ; as apostilas geradas ficam na pasta escolhida pelo usuário e nunca são apagadas
SectionEnd
