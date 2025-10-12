FROM python:3.10-alpine

# 设置元数据
LABEL maintainer="LLM Gateway Team"
LABEL description="LLM Gateway - Multi-provider LLM API proxy service"
LABEL version="1.0.0"

# 设置时区
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 安装系统依赖
RUN apk add --no-cache musl-dev openssl-dev libffi-dev gcc

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p /app/log

# 暴露端口
EXPOSE 8100

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8100/api_usage', timeout=5)"

# 启动命令
CMD ["python3", "app.py"]
