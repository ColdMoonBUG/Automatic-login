@echo off
CHCP 65001 > NUL

SETLOCAL ENABLEDELAYEDEXPANSION

REM 校园网监控后台自启动配置脚本
REM 运行此脚本将创建一个计划任务，使 auth_monitor.py 在用户登录时自动后台运行。

SET "SCRIPT_DIR=%~dp0"
IF "%SCRIPT_DIR:~-1%"=="\" SET "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

SET "PYTHON_SCRIPT_NAME=auth_monitor.py"
SET "FULL_SCRIPT_PATH=%SCRIPT_DIR%\%PYTHON_SCRIPT_NAME%"

SET "TASK_NAME=CampusNetAuthMonitorStartup"

SET "PYTHON_EXECUTABLE="
FOR /F "usebackq tokens=*" %%P IN (`where pythonw.exe 2^>nul`) DO (
    SET "PYTHON_EXECUTABLE=%%P"
    GOTO FoundPythonExecutable
)
FOR /F "usebackq tokens=*" %%P IN (`where pyw.exe 2^>nul`) DO (
    SET "PYTHON_EXECUTABLE=%%P"
    GOTO FoundPythonExecutable
)

IF NOT DEFINED PYTHON_EXECUTABLE (
    echo [错误] 未能在系统路径中找到 pythonw.exe 或 pyw.exe。
    echo 请确保您已正确安装Python，并将其添加到了系统的PATH环境变量中。
    goto EndScript
)

:FoundPythonExecutable
echo [信息] 将使用Python可执行文件: "%PYTHON_EXECUTABLE%"
echo [信息] Python脚本路径: "%FULL_SCRIPT_PATH%"
echo [信息] 脚本工作目录将设置为: "%SCRIPT_DIR%"

SET "TASK_COMMAND=cmd /c cd /d \"%SCRIPT_DIR%\" && \"%PYTHON_EXECUTABLE%\" \"%FULL_SCRIPT_PATH%\""

echo [操作] 正在尝试创建/更新计划任务: "%TASK_NAME%"
echo       任务命令: %TASK_COMMAND%
echo       触发器: 用户登录时

SCHTASKS /CREATE /TN "%TASK_NAME%" /TR "%TASK_COMMAND%" /SC ONLOGON /F /RL HIGHEST 

IF !ERRORLEVEL! EQU 0 (
    echo [成功] 计划任务 "%TASK_NAME%" 已成功创建或更新。
    echo        监控脚本 auth_monitor.py 将在您下次登录时自动在后台启动。
) ELSE (
    echo [错误] 创建/更新计划任务 "%TASK_NAME%" 失败。错误代码: !ERRORLEVEL!
    echo        如果您遇到权限问题，请尝试以管理员身份运行此 .bat 脚本。
)

:EndScript
echo 按任意键退出...
pause
ENDLOCAL
