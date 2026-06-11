@echo off
REM 开发快速部署
REM   双击或 dev_deploy       -> 仅后端热更新（docker cp + 重启，~15秒）
REM   dev_deploy --web        -> 后端热更新 + 前端重构（~2分钟）
REM   正式部署请用 sync_and_deploy.ps1
echo ===== FreeCADAI Quick Dev Deploy =====
python "%~dp0scripts\dev_deploy.py" %*
if %ERRORLEVEL% EQU 0 (
    echo Done.
) else (
    echo.
    echo 部署出错，按任意键退出...
    pause > nul
)
