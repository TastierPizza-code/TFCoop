@echo off
setlocal
cd /d "%~dp0.."
call prototype\build-native.cmd || exit /b 1
py -3.10 -m unittest discover -s prototype\tests -v || exit /b 1
py -3.10 prototype\mod\tf2_strict_probe_1\tests\test_literal_lua.py || exit /b 1
py -3.10 -m prototype.strict_sync.smoke || exit /b 1
echo All prototype checks passed. TF2 was not launched or modified.
