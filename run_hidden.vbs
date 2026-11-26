Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\Users\User\Desktop\tg-ai-agent && .venv\Scripts\python.exe answer_calls.py --delay 10 --listen 15 --voice uz-m >> C:\Users\User\Desktop\tg-ai-agent\agent.log 2>&1", 0, False

