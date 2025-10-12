# 部署指南

本文档介绍如何部署和使用LLM Gateway的Docker镜像。

## 快速部署

### 使用发布的Docker镜像（推荐）

1. **下载配置文件模板**
```bash
# 下载配置文件模板
curl -O https://raw.githubusercontent.com/your-username/llm-gateway/main/config.yaml.example
cp config.yaml.example config.yaml
```

2. **编辑配置文件**
```bash
# 编辑配置文件，添加您的API密钥
vim config.yaml
```

3. **使用Docker Compose部署**
```bash
# 下载docker-compose.yml
curl -O https://raw.githubusercontent.com/your-username/llm-gateway/main/docker-compose.yml

# 启动服务
docker-compose up -d
```

4. **验证部署**
```bash
# 检查服务状态
docker-compose ps

# 测试API
curl http://localhost:8100/v1/models
```

### 从源码构建（开发环境）

1. **克隆仓库**
```bash
git clone https://github.com/your-username/llm-gateway.git
cd llm-gateway
```

2. **构建并启动**
```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d
```

## Docker镜像发布

### 发布新版本

1. **准备发布环境**
```bash
# 登录Docker Hub
docker login

# 确保脚本可执行
chmod +x docker-publish.sh
```

2. **发布镜像**
```bash
# 执行完整发布流程
./docker-publish.sh all

# 或者分步执行
./docker-publish.sh build    # 仅构建
./docker-publish.sh test     # 构建并测试
./docker-publish.sh push     # 构建、测试并推送
```

### 镜像标签策略

- `latest`: 最新稳定版本
- `1.0.0`: 具体版本号
- `develop`: 开发版本

## 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| TZ | Asia/Shanghai | 时区设置 |

### 端口映射

| 容器端口 | 主机端口 | 服务 | 说明 |
|----------|----------|------|------|
| 8100 | 8100 | LLM Gateway | API服务端口 |
| 6333 | 6333 | Qdrant | 向量数据库HTTP端口 |
| 6334 | 6334 | Qdrant | 向量数据库gRPC端口 |

### 数据卷

- `./config.yaml:/app/config.yaml:ro`: 配置文件（只读）
- `llm-gateway-logs:/app/log`: 日志目录

## 生产环境部署建议

### 安全配置

1. **使用HTTPS**
```yaml
# 在反向代理中配置SSL
services:
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
```

2. **访问控制**
```yaml
# 在docker-compose.yml中添加网络限制
networks:
  llm-gateway-net:
    driver: bridge
    internal: false
```

### 监控和日志

1. **日志收集**
```yaml
# 添加日志驱动
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

2. **健康检查**
```yaml
# 健康检查配置（已在docker-compose.yml中包含）
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8100/api_usage', timeout=5)"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## 故障排除

### 常见问题

1. **端口冲突**
```bash
# 检查端口占用
netstat -tulpn | grep :8100

# 修改端口映射
ports:
  - '8200:8100'  # 主机端口:容器端口
```

2. **权限问题**
```bash
# 确保配置文件可读
chmod 644 config.yaml

# 检查日志目录权限
docker exec llm-gateway ls -la /app/log
```

3. **镜像拉取失败**
```bash
# 检查网络连接
ping hub.docker.com

# 使用镜像加速器
# 在/etc/docker/daemon.json中添加
{
  "registry-mirrors": ["https://registry.docker-cn.com"]
}
```

### 日志查看

```bash
# 查看服务日志
docker-compose logs api

# 实时查看日志
docker-compose logs -f api

# 查看特定时间段的日志
docker-compose logs --since="2024-01-01" api
```

## 更新部署

### 更新到新版本

1. **拉取最新镜像**
```bash
docker-compose pull
```

2. **重启服务**
```bash
docker-compose up -d
```

3. **验证更新**
```bash
docker-compose ps
curl http://localhost:8100/v1/models
```

### 回滚到旧版本

```bash
# 指定版本启动
docker-compose down
docker-compose up -d --image your-dockerhub-username/llm-gateway:1.0.0
```

## 性能优化

### 资源限制

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
```

### 数据库优化

```yaml
services:
  qdrant:
    environment:
      - QDRANT__STORAGE__OPTIMIZERS__INDEXING_THRESHOLD=10000
      - QDRANT__STORAGE__OPTIMIZERS__MEMORY_THRESHOLD=0.8
```

## 支持

如有部署问题，请参考：
- [GitHub Issues](https://github.com/your-username/llm-gateway/issues)
- [文档](README.md)
- [配置说明](config.yaml.example)
