@echo off
setlocal
set "TF2COOP_VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%TF2COOP_VCVARS%" (
  echo Visual Studio 2022 Build Tools mit C++ x64 fehlen.
  exit /b 1
)
call "%TF2COOP_VCVARS%" >nul
cd /d "%~dp0"
if not exist out mkdir out
set "TF2COOP_SRC=..\upstream\tpf2-multiplayer\bridge\src"
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\net.cpp" /Fo:out\net.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\savexfer.cpp" /Fo:out\savexfer.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\hook.cpp" /Fo:out\hook.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\simhook.cpp" /Fo:out\simhook.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\buyhook.cpp" /Fo:out\buyhook.obj || exit /b 1
ml64 /nologo /c /Fo out\simsteprelay.obj "%TF2COOP_SRC%\simsteprelay.asm" || exit /b 1
ml64 /nologo /c /Fo out\buyrelay.obj "%TF2COOP_SRC%\buyrelay.asm" || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\bridge_main.cpp" /Fo:out\bridge.obj || exit /b 1
link /nologo /DLL /OUT:out\tpf2_bridge_mp.dll out\net.obj out\savexfer.obj out\hook.obj out\simhook.obj out\simsteprelay.obj out\buyhook.obj out\buyrelay.obj out\bridge.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /LD "%TF2COOP_SRC%\proxy_alut.cpp" /Fe:out\alut.dll /Fo:out\proxy_alut.obj || exit /b 1
cl /nologo /O2 /MT /W3 /EHsc /c "%TF2COOP_SRC%\slice_hook.cpp" /Fo:out\slice_hook.obj || exit /b 1
ml64 /nologo /c /Fo out\deferrelay_slice.obj "%TF2COOP_SRC%\deferrelay_slice.asm" || exit /b 1
link /nologo /DLL /OUT:out\tpf2_slice.dll out\hook.obj out\slice_hook.obj out\deferrelay_slice.obj || exit /b 1
echo TF2 Co-op native build OK. No files installed into the game.

