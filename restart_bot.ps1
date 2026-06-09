# Kill existing pythonw.exe (Discord bot)
Get-Process -Name "pythonw" -ErrorAction SilentlyContinue | ForEach-Object {
    "Killing PID $($_.Id): $($_.ProcessName)" | Out-File "C:\Users\USER\aaa\restart_log.txt" -Append -Encoding UTF8
    $_.Kill()
}

Start-Sleep -Seconds 2

# Start fresh bot process
$proc = Start-Process -FilePath "C:\Python314\pythonw.exe" `
    -ArgumentList "C:\Users\USER\aaa\discord_bot.py" `
    -WorkingDirectory "C:\Users\USER\aaa" `
    -PassThru

"Started new bot PID: $($proc.Id)" | Out-File "C:\Users\USER\aaa\restart_log.txt" -Append -Encoding UTF8
"Done at $(Get-Date)" | Out-File "C:\Users\USER\aaa\restart_log.txt" -Append -Encoding UTF8
