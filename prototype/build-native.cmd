@echo off
setlocal
set "TF2PROTO_VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%TF2PROTO_VCVARS%" (
  echo Visual Studio 2022 Build Tools with C++ x64 are required.
  exit /b 1
)
call "%TF2PROTO_VCVARS%" >nul
cd /d "%~dp0native"
if not exist out mkdir out
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /c step_probe.cpp /Fo:out\step_probe.obj || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /c probe_runtime.cpp /Fo:out\probe_runtime.obj || exit /b 1
link /nologo /DLL /OUT:out\tf2_step_probe.dll /IMPLIB:out\tf2_step_probe.lib out\step_probe.obj out\probe_runtime.obj || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /LD proxy_probe.cpp /Fe:out\probe_alut.dll /Fo:out\proxy_probe.obj /link /IMPLIB:out\probe_alut.lib || exit /b 1
ml64 /nologo /c /Fo out\step_probe_test_asm.obj step_probe_test.asm || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /DTF2_STEP_PROBE_TEST /c step_probe.cpp /Fo:out\step_probe_for_test.obj || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc step_probe_test.cpp out\step_probe_for_test.obj out\step_probe_test_asm.obj /DTF2_STEP_PROBE_TEST /Fe:out\step_probe_test.exe /Fo:out\step_probe_test.obj /link /IMPLIB:out\step_probe_test.lib || exit /b 1
out\step_probe_test.exe || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /DTF2_STEP_PROBE_TEST /c probe_runtime.cpp /Fo:out\probe_runtime_for_test.obj || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /DTF2_STEP_PROBE_TEST probe_runtime_test.cpp out\probe_runtime_for_test.obj out\step_probe_for_test.obj /Fe:out\probe_runtime_test.exe /Fo:out\probe_runtime_test.obj /link /IMPLIB:out\probe_runtime_test.lib || exit /b 1
out\probe_runtime_test.exe || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc /c deferred_command.cpp /Fo:out\deferred_command.obj || exit /b 1
lib /nologo /OUT:out\tf2_deferred_command.lib out\deferred_command.obj || exit /b 1
cl /nologo /std:c++17 /O2 /MT /W4 /EHsc deferred_command_test.cpp out\deferred_command.obj /Fe:out\deferred_command_test.exe /Fo:out\deferred_command_test.obj || exit /b 1
out\deferred_command_test.exe || exit /b 1
echo Native prototype build and contract tests passed. No game files installed.
