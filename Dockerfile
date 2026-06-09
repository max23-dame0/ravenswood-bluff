# 使用官方轻量级 Python 3.11 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装必要的系统构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖配置文件以缓存构建层
COPY pyproject.toml .

# 创建空的 src 目录，防止 setuptools 安装报错
RUN mkdir src && touch src/__init__.py

# 安装依赖包
RUN pip install --no-cache-dir .

# 复制项目全部内容
COPY . .

# 声明容器对外暴露的端口
EXPOSE 8000

# 设置默认环境变量（可通过 docker-compose 或 run 命令行进行覆盖）
ENV BOTC_HOST=0.0.0.0
ENV BOTC_PORT=8000
ENV BOTC_BACKEND=auto

# 启动命令
CMD ["python", "-m", "src.api.server"]
