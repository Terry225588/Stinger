@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Stinger

echo Stinger
echo 这个窗口会留下来。安装失败时请把上面的英文报错整段保留。
echo 尚未在 Windows 10 上验证过本脚本。
echo.

set "PYEXE="
set "PYARG="
if defined SCREENMATCH_PYTHON call :accept "%SCREENMATCH_PYTHON%"
if not defined PYEXE if exist "%~dp0..\Python312\python.exe" call :accept "%~dp0..\Python312\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" call :accept "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3, 12) else 1)" 1>nul 2>nul
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARG=-3.12"
    )
)
if not defined PYEXE (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3, 12) else 1)" 1>nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE goto no_python
echo 使用 Python: %PYEXE% %PYARG%

if not exist ".venv\Scripts\python.exe" (
    echo 正在用 Python 3.12 创建虚拟环境 .venv ...
    "%PYEXE%" %PYARG% -m venv .venv
    if errorlevel 1 goto venv_fail
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
"%VENV_PY%" -c "import openpyxl,rapidocr_onnxruntime,mss,numpy,cv2,onnxruntime,PIL" 1>nul 2>nul
if errorlevel 1 goto install_deps
goto check_tk

:install_deps
echo 依赖还没装齐。开始安装，这一步需要联网，时间会比较长。
"%VENV_PY%" -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto pip_fail

:check_tk
"%VENV_PY%" -c "import tkinter" 1>nul 2>nul
if errorlevel 1 goto no_tk

set "PYTHONPATH=%CD%\src"
"%VENV_PY%" -c "from screenmatch.ocr_engine import bundled_model_report; root, missing = bundled_model_report(); raise SystemExit('\n'.join(missing) if missing else 0)"
if errorlevel 1 goto no_model

echo 正在打开界面。识别使用安装包里的本地模型，不把题目发到云端。
"%VENV_PY%" -m screenmatch
if errorlevel 1 goto run_fail
goto end

:no_python
echo.
echo 没有找到 64 位 Python 3.12。不要求把它加进系统 PATH，也不要求安装 py launcher。
echo 可以设置环境变量 SCREENMATCH_PYTHON 为 python.exe 的完整路径。
echo 也可以把 Python 放在本目录上一级的 Python312\python.exe。
echo 或者使用 python.org 的用户安装目录 %%LOCALAPPDATA%%\Programs\Python\Python312\python.exe。
echo 不要用 3.11：当前 numpy 2.5.5 没有 Windows 版 3.11 轮子。
echo 不要用 3.13：rapidocr-onnxruntime 1.4.4 只声明支持到 3.12。
goto fail

:venv_fail
echo.
echo 创建虚拟环境失败。请确认 Python 3.12 能在命令行运行，并且当前目录可写。
goto fail

:pip_fail
echo.
echo 依赖安装失败。请向上翻看 pip 的英文报错。
echo 常见原因：没有网络、Python 不是 3.12、或杀毒软件拦住了虚拟环境。
echo 装好之前，识别不能离线进行。
goto fail

:no_tk
echo.
echo 这个 Python 没有 tkinter。请改用 python.org 的安装包，安装时勾选 tcl/tk。
goto fail

:no_model
echo.
echo 安装包里没有找到本地 OCR 模型。程序不会改走云端识别。
echo 请确认 rapidocr-onnxruntime 1.4.4 安装完整，模型应在 site-packages\rapidocr_onnxruntime\models。
goto fail

:run_fail
echo.
echo 程序退出时带有错误。若界面没有出现，请把上面的报错保留下来。
goto fail

:fail
echo.
pause
exit /b 1

:accept
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3, 12) else 1)" 1>nul 2>nul
if not errorlevel 1 set "PYEXE=%~1"
goto :eof

:end
endlocal
