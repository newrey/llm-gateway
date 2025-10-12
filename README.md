# LLM Gateway

一个功能强大的多API提供商LLM代理服务，支持OpenAI兼容的API接口，提供智能负载均衡、速率限制管理和实时监控功能。

## 功能特性

- 🚀 **多API提供商支持**：支持多个LLM API提供商，自动故障转移
- ⚡ **智能负载均衡**：基于速率限制和可用性自动选择最佳提供商
- 🔒 **速率限制管理**：支持RPM、TPM、RPD、TPR等多种限制策略
- 📊 **实时监控**：提供API使用统计和健康检测功能
- 🎯 **OpenAI兼容**：完全兼容OpenAI API接口规范
- 🐳 **Docker支持**：提供完整的Docker部署方案
- 🔧 **Web管理界面**：直观的Web界面进行配置管理
- 📈 **流式响应**：支持流式响应和实时日志记录

## 快速开始

### 环境要求

- Python 3.10+
- Docker (可选)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

1. 复制配置文件模板：
```bash
cp config.yaml.example config.yaml
```

2. 编辑 `config.yaml` 文件，配置您的API提供商信息：

```yaml
api_provider:
  your_provider:
    base_url: https://api.example.com/v1
    api_key: your_api_key_here
    limits:
      rpm: 60    # 每分钟请求数
      tpm: 10000 # 每分钟token数
      rpd: 1000  # 每日请求数
      tpr: 4000  # 每次请求最大token数

model_config:
  gpt-4o:
    your_provider:
      alias: gpt-4o  # 可选，如果提供商使用的模型名称不同
      enable: true   # 是否启用该提供商
```

### 启动服务

```bash
python app.py
```

或者使用Docker：

```bash
docker-compose up -d
```

服务将在 http://localhost:8100 启动。

## API使用

### 基本用法

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8100/v1",
    api_key="any_key"  # 任意值，实际API密钥在配置文件中配置
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=False
)

print(response.choices[0].message.content)
```

### 流式响应

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

### 自动模型选择

```python
# 使用"auto"模型，系统会自动选择合适的模型
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## 管理界面

访问 http://localhost:8100/admin 打开管理界面，可以：

- 查看和修改模型配置
- 监控API使用情况
- 执行健康检测
- 重置速率限制
- 查看错误日志

## 配置说明

### API提供商配置

每个API提供商需要配置以下参数：

- `base_url`: API基础URL
- `api_key`: API密钥
- `limits`: 速率限制配置
  - `rpm`: 每分钟请求数限制
  - `tpm`: 每分钟token数限制
  - `rpd`: 每日请求数限制
  - `tpr`: 每次请求最大token数限制

### 模型配置

每个模型可以配置多个提供商：

- `alias`: 提供商使用的实际模型名称（可选）
- `enable`: 是否启用该提供商

## 部署

### Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 生产环境部署

建议使用反向代理（如Nginx）和进程管理器（如PM2）进行生产环境部署。

## 故障排除

### 常见问题

1. **API连接失败**：检查API密钥和base_url配置
2. **速率限制错误**：调整limits配置或添加更多API提供商
3. **模型不可用**：确保模型在提供商处可用且已启用

### 日志查看

日志文件位于 `log/` 目录：
- `app.log`: 应用日志
- `agent_interactions.log`: API交互日志

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 支持

如有问题，请提交Issue或联系维护者。
