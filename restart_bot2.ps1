$log = "C:\Users\USER\aaa\restart_log2.txt"
"=== restart_bot2.ps1 started $(Get-Date) ===" | Out-File $log -Encoding UTF8

# Kill existing pythonw processes
try {
    $procs = Get-Process -Name "pythonw" -ErrorAction Stop
    foreach ($p in $procs) {
        "Killing PID=$($p.Id)" | Out-File $log -Append -Encoding UTF8
        $p.Kill()
        Start-Sleep -Milliseconds 500
    }
} catch {
    "No pythonw process or error: $_" | Out-File $log -Append -Encoding UTF8
}

Start-Sleep -Seconds 2

# Start fresh bot
try {
    $proc = Start-Process `
        -FilePath "C:\Python314\pythonw.exe" `
        -ArgumentList "discord_bot.py" `
        -WorkingDirectory "C:\Users\USER\aaa" `
        -PassThru -ErrorAction Stop
    "Started new bot PID=$($proc.Id)" | Out-File $log -Append -Encoding UTF8
} catch {
    "Failed to start bot: $_" | Out-File $log -Append -Encoding UTF8
}

"=== Done $(Get-Date) ===" | Out-File $log -Append -Encoding UTF8
