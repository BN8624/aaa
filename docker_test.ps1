$out = & docker run --rm python:3.11-slim python -c "print('docker_ok')" 2>&1
$code = $LASTEXITCODE
"exit_code=$code" | Out-File -FilePath "C:\Users\USER\aaa\docker_test_out.txt" -Encoding UTF8
$out | Out-File -FilePath "C:\Users\USER\aaa\docker_test_out.txt" -Append -Encoding UTF8
