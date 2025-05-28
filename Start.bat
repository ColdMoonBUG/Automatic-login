
@echo off
CHCP 65001 >NUL
SETLOCAL ENABLEDELAYEDEXPANSION

SET "LOG_FILE=%~dp0task_setup.log"
echo [%date% %time%] 任务配置开始 >> "%LOG_FILE%"

SET "PY_SCRIPT=%~dp0auth_monitor.py"
SET "TASK_NAME=CampusNetAuthMonitor"

:: 验证Python脚本存在
if not exist "%PY_SCRIPT%" (
    echo [错误] 未找到脚本文件: %PY_SCRIPT% | tee -a "%LOG_FILE%"
    goto ERROR
)

:: 智能选择Python解释器
SET "PY_EXE="
for %%I in (pythonw.exe pyw.exe) do (
    where %%I >nul 2>&1 && (
        SET "PY_EXE=%%I"
        goto FOUND_PYTHON
    )
)

:ERROR
echo [错误] 需要Python环境支持 | tee -a "%LOG_FILE%"
goto END

:FOUND_PYTHON
:: 任务存在检测
schtasks /query /tn "%TASK_NAME%" >nul 2>&1 && (
    echo [警告] 任务已存在，执行更新操作 | tee -a "%LOG_FILE%"
    SET "TASK_ACTION=/change"
) || SET "TASK_ACTION=/create"

:: 创建/更新任务
schtasks %TASK_ACTION% /tn "%TASK_NAME%" ^
    /tr "\"%PY_EXE%\" \"%PY_SCRIPT%\"" ^
    /sc onlogon /ru SYSTEM /rl HIGHEST /f /it

if %errorlevel% neq 0 (
    echo [错误] 任务配置失败(代码%errorlevel%) | tee -a "%LOG_FILE%"
) else (
    echo [成功] 计划任务已配置 | tee -a "%LOG_FILE%"
    :: 立即测试执行
    start "" "%PY_EXE%" "%PY_SCRIPT%"
)

:END
echo 操作日志已保存到: %LOG_FILE%
pause
