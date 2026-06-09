@echo off
chcp 65001 > nul
title 鸦木布拉夫小镇 (Ravenswood Bluff) 游戏服务器启动器

echo =======================================================================
echo           鸦木布拉夫小镇 (Ravenswood Bluff) 游戏服务器启动器
echo =======================================================================
echo.

:: 检查本地虚拟环境是否存在
if not exist ".venv\Scripts\activate.bat" (
    echo [错误] 未在当前目录下检测到 .venv 虚拟环境！
    echo -------------------------------------------------------------------
    echo 请按照以下步骤配置您的运行环境：
    echo   1. 确保已安装 Python 3.11+。
    echo   2. 在项目根目录下打开终端，创建虚拟环境：
    echo      python -m venv .venv
    echo   3. 激活虚拟环境并安装依赖：
    echo      .venv\Scripts\activate
    echo      pip install -e "."
    echo -------------------------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo [信息] 正在激活虚拟环境...
call .venv\Scripts\activate.bat

echo [信息] 正在启动 API 服务器...
echo [提示] 启动完成后，您可以使用终端打印的局域网 IP 邀请局域网内或 Tailscale 网络下的玩家加入。
echo.

python -m src.api.server

if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务器异常退出！错误代码：%errorlevel%
    pause
)
