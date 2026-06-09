$stdout = "C:\Users\USER\aaa\logs\discord\docker_run_h4_3_stdout.log"
$stderr = "C:\Users\USER\aaa\logs\discord\docker_run_h4_3_stderr.log"
$meta   = "C:\Users\USER\aaa\logs\discord\docker_run_h4_3_meta.log"

"started_at: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss+09:00')" | Out-File $meta -Encoding UTF8

$proc = Start-Process `
    -FilePath "C:\Python314\python.exe" `
    -ArgumentList "discord_bot.py", "--pipeline-docker", "h4_3" `
    -WorkingDirectory "C:\Users\USER\aaa" `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError  $stderr `
    -NoNewWindow -PassThru

"pid: $($proc.Id)" | Out-File $meta -Append -Encoding UTF8
"launched: ok" | Out-File $meta -Append -Encoding UTF8
