Unicode True
SetCompressor /SOLID lzma

; --------------------------------------------------------------------------
; Defines (VERSION and EXE_SRC can be overridden from the command line)
; --------------------------------------------------------------------------
!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef EXE_SRC
  !define EXE_SRC "..\dist\FFmpegCropTool.exe"
!endif

!define APP_NAME      "FFmpeg Crop Tool"
!define APP_EXE       "FFmpegCropTool.exe"
!define APP_PUBLISHER "patchamama"
!define APP_URL       "https://github.com/patchamama/ffmpeg-video-crop-tool"
!define PROG_ID       "FFmpegCropTool.VideoFile"
!define REG_APP       "Software\FFmpegCropTool"
!define REG_UNINST    "Software\Microsoft\Windows\CurrentVersion\Uninstall\FFmpegCropTool"

Name    "${APP_NAME} ${VERSION}"
OutFile "..\dist\FFmpegCropTool-windows-installer.exe"
InstallDir          "$PROGRAMFILES64\FFmpegCropTool"
InstallDirRegKey    HKLM "${REG_APP}" "InstallDir"
RequestExecutionLevel admin
BrandingText        "${APP_NAME} ${VERSION}"

; --------------------------------------------------------------------------
; Modern UI
; --------------------------------------------------------------------------
!include "MUI2.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN         "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT    "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_LINK        "Project on GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION "${APP_URL}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; --------------------------------------------------------------------------
; Component descriptions
; --------------------------------------------------------------------------
LangString DESC_Main     ${LANG_ENGLISH} "Application files (required)."
LangString DESC_FileAssoc ${LANG_ENGLISH} "Add 'Open with FFmpeg Crop Tool' to the right-click menu for video files."
LangString DESC_StartMenu ${LANG_ENGLISH} "Create shortcuts in the Start Menu."
LangString DESC_Desktop   ${LANG_ENGLISH} "Create a shortcut on the Desktop."

; --------------------------------------------------------------------------
; Macros for registering / unregistering each video extension
; --------------------------------------------------------------------------
!macro _RegExt EXT
  ; Right-click "Open with FFmpeg Crop Tool" context menu entry
  WriteRegStr HKCR "${EXT}\shell\FFmpegCropTool"           ""      "Open with FFmpeg Crop Tool"
  WriteRegStr HKCR "${EXT}\shell\FFmpegCropTool"           "Icon"  '"$INSTDIR\${APP_EXE}",0'
  WriteRegStr HKCR "${EXT}\shell\FFmpegCropTool\command"   ""      '"$INSTDIR\${APP_EXE}" "%1"'
  ; "Open With" dialog association
  WriteRegStr HKCR "${EXT}\OpenWithProgids"                "${PROG_ID}" ""
!macroend

!macro _UnregExt EXT
  DeleteRegKey   HKCR "${EXT}\shell\FFmpegCropTool"
  DeleteRegValue HKCR "${EXT}\OpenWithProgids" "${PROG_ID}"
!macroend

; --------------------------------------------------------------------------
; Sections
; --------------------------------------------------------------------------

Section "!${APP_NAME} (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "${EXE_SRC}"

  ; Register ProgID (appears in "Open With > Choose another app")
  WriteRegStr HKCR "${PROG_ID}"                       ""    "Video file"
  WriteRegStr HKCR "${PROG_ID}\DefaultIcon"           ""    '"$INSTDIR\${APP_EXE}",0'
  WriteRegStr HKCR "${PROG_ID}\shell\open\command"    ""    '"$INSTDIR\${APP_EXE}" "%1"'

  ; Register in Add/Remove Programs
  WriteRegStr   HKLM "${REG_UNINST}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKLM "${REG_UNINST}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKLM "${REG_UNINST}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr   HKLM "${REG_UNINST}" "URLInfoAbout"    "${APP_URL}"
  WriteRegStr   HKLM "${REG_UNINST}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKLM "${REG_UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKLM "${REG_UNINST}" "DisplayIcon"     '"$INSTDIR\${APP_EXE}",0'
  WriteRegDWORD HKLM "${REG_UNINST}" "NoModify"        1
  WriteRegDWORD HKLM "${REG_UNINST}" "NoRepair"        1
  WriteRegStr   HKLM "${REG_APP}"    "InstallDir"      "$INSTDIR"
  WriteRegStr   HKLM "${REG_APP}"    "Version"         "${VERSION}"

  ; Compute estimated size for Add/Remove Programs
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "${REG_UNINST}" "EstimatedSize" $0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Video file associations" SecFileAssoc
  !insertmacro _RegExt ".mp4"
  !insertmacro _RegExt ".mkv"
  !insertmacro _RegExt ".avi"
  !insertmacro _RegExt ".mov"
  !insertmacro _RegExt ".webm"
  !insertmacro _RegExt ".m4v"
  !insertmacro _RegExt ".wmv"
  !insertmacro _RegExt ".flv"

  ; Notify Explorer to refresh icons / context menus
  System::Call 'shell32.dll::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'
SectionEnd

Section "Start Menu shortcuts" SecStartMenu
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                  "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
                 "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}      $(DESC_Main)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFileAssoc} $(DESC_FileAssoc)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_StartMenu)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop}   $(DESC_Desktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; --------------------------------------------------------------------------
; Uninstaller
; --------------------------------------------------------------------------

Section "Uninstall"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir  "$INSTDIR"

  ; Remove shortcuts
  Delete "$SMPROGRAMS\${APP_NAME}\*.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; Remove ProgID
  DeleteRegKey HKCR "${PROG_ID}"

  ; Remove file associations
  !insertmacro _UnregExt ".mp4"
  !insertmacro _UnregExt ".mkv"
  !insertmacro _UnregExt ".avi"
  !insertmacro _UnregExt ".mov"
  !insertmacro _UnregExt ".webm"
  !insertmacro _UnregExt ".m4v"
  !insertmacro _UnregExt ".wmv"
  !insertmacro _UnregExt ".flv"

  ; Refresh Explorer
  System::Call 'shell32.dll::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  ; Remove from Add/Remove Programs
  DeleteRegKey HKLM "${REG_UNINST}"
  DeleteRegKey HKLM "${REG_APP}"
SectionEnd
