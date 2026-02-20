@echo off
REM Ptero Dactyl Games: Agent Runner
REM Запускает Claude Code для выполнения задачи из случайного проекта

cd /d "C:\Ptero Dactyl Games"

REM Логирование
set LOGFILE=studio\logs\%date:~-4,4%-%date:~-7,2%-%date:~-10,2%.log
echo [%date% %time%] Starting agent run >> %LOGFILE%

REM Запуск агента
claude -p "Ты агент студии Ptero Dactyl Games. Твоя задача: 1) Открой BACKLOG.md каждого проекта (backpack_hero, babylon, hamster). 2) Найди проект с задачей в секции 'В работе' или возьми первую из 'Высокий приоритет'. 3) Выполни эту задачу. 4) Отметь задачу как [x] с датой. 5) Запиши что сделал в CHANGELOG.md проекта. 6) Сделай git commit если проект под git." >> %LOGFILE% 2>&1

echo [%date% %time%] Agent run completed >> %LOGFILE%
