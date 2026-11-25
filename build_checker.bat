@echo off
setlocal
set PATH=%USERPROFILE%\.cargo\bin;%PATH%
echo Building Calendar Zero-CRT Rust checker (checker.dll + checker_ultra.exe)...
cargo rustc --release --lib -- -C link-arg=-nostdlib -C link-arg=-Wl,-e,DllMain -lkernel32 -ladvapi32
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
cargo rustc --release --bin checker_ultra -- -C link-arg=-nostdlib -C link-arg=-Wl,-e,checker_entry -C link-arg=-Wl,--subsystem,windows -lkernel32 -ladvapi32
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
copy /Y target\release\checker.dll checker.dll >nul
copy /Y target\release\checker_ultra.exe checker_ultra.exe >nul
for %%A in (checker.dll checker_ultra.exe) do echo Built %%A (%%~zA bytes)
