@echo off
echo [docker_test] Testing Docker...
docker run --rm python:3.11-slim python -c "print('docker_ok')" > C:\Users\USER\aaa\docker_test_out.txt 2>&1
echo exit_code=%errorlevel% >> C:\Users\USER\aaa\docker_test_out.txt
echo [docker_test] Done. Check docker_test_out.txt
