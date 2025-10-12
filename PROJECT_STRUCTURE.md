# 项目结构

```
llm-gateway/
├── .github/                    # GitHub Actions 配置
│   └── workflows/
│       └── ci.yml             # 持续集成配置
├── static/                     # 静态文件目录
│   └── admin.html             # 管理界面前端文件
├── .gitignore                 # Git忽略文件配置
├── app.py                     # 主应用文件
├── config.yaml                # 配置文件（不包含敏感信息）
├── config.yaml.example        # 配置文件模板
├── CONTRIBUTING.md            # 贡献指南
├── CODE_OF_CONDUCT.md         # 行为准则
├── docker-compose.yml         # Docker Compose 配置
├── Dockerfile                 # Docker 镜像构建文件
├── LICENSE                    # MIT 许可证
├── PROJECT_STRUCTURE.md       # 项目结构说明（本文件）
├── README.md                  # 项目说明文档
├── requirements.txt           # Python 依赖列表
└── test_basic.py              # 基础测试文件
```

## 文件说明

### 核心文件

- **app.py**: 主应用文件，包含FastAPI应用、路由处理、速率限制器等核心功能
- **config.yaml**: 配置文件，包含API提供商和模型配置（已移除敏感信息）
- **config.yaml.example**: 配置文件模板，供用户参考配置

### 文档文件

- **README.md**: 项目主要文档，包含功能特性、快速开始、API使用说明等
- **CONTRIBUTING.md**: 贡献指南，说明如何为项目做贡献
- **CODE_OF_CONDUCT.md**: 行为准则，确保社区友好环境
- **PROJECT_STRUCTURE.md**: 项目结构说明（本文件）

### 部署文件

- **Dockerfile**: Docker镜像构建文件
- **docker-compose.yml**: Docker Compose配置，支持快速部署
- **requirements.txt**: Python依赖包列表

### 配置和工具文件

- **.gitignore**: Git忽略规则
- **.github/workflows/ci.yml**: GitHub Actions持续集成配置

### 静态资源

- **static/admin.html**: Web管理界面前端文件

## 目录结构设计原则

1. **简洁性**: 保持目录结构简单明了，避免过度嵌套
2. **模块化**: 按功能组织文件，便于维护和扩展
3. **标准化**: 遵循Python和开源项目的最佳实践
4. **可扩展性**: 为未来功能扩展预留空间

## 未来扩展建议

随着项目发展，可以考虑以下结构调整：

1. **模块化重构**:
   ```
   src/
   ├── api/           # API路由和端点
   ├── core/          # 核心功能（速率限制、配置管理等）
   ├── models/        # 数据模型
   └── utils/         # 工具函数
   ```

2. **测试目录**:
   ```
   tests/
   ├── unit/          # 单元测试
   ├── integration/   # 集成测试
   └── fixtures/      # 测试数据
   ```

3. **文档目录**:
   ```
   docs/
   ├── api/           # API文档
   ├── deployment/    # 部署文档
   └── development/   # 开发文档
   ```

当前结构已经足够支持项目的核心功能，未来可以根据实际需求进行适当调整。
