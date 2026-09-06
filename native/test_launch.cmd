@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
if not exist out mkdir out
cl /nologo /EHsc /W3 /MT test_launch.cpp /Fe:out\test_launch.exe /Fo:out\test_launch.obj || exit /b 1
out\test_launch.exe
