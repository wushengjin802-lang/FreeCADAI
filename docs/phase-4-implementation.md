# 阶段 4 实现说明

## 已实现内容

阶段 4 将 FreeCADAI 从单机插件扩展为“本地 FreeCAD 插件 + 云端 SaaS 后端”的原型架构。

已完成：

- 插件设置页新增 `服务模式`。
- 支持 `本地直连 LLM` 和 `云端 SaaS 服务` 两种模式。
- 插件云端模式新增：
  - `SaaS Base URL`
  - `SaaS API Key`
  - `Project ID`
  - `执行后回传结果`
- 新增插件云端客户端：

```text
freecad_ai/cloud/client.py
```

- `调用 LLM 生成脚本` 支持云端 `/api/v1/plugin/generate`。
- `调用 LLM 修复脚本` 支持云端 `/api/v1/plugin/repair`。
- `按参数重新生成` 支持云端 `/api/v1/plugin/regenerate`。
- `执行脚本` 成功或失败后可回传 `/api/v1/plugin/execution-reports`。
- 保留本地直连 OpenAI-compatible `/chat/completions` 能力。
- 保留本地示例脚本能力，便于无 API 时测试 FreeCAD 执行链路。
- 新增 FastAPI SaaS 后端骨架。
- 新增 MySQL SQLAlchemy 数据模型。
- 新增 Docker Compose 本地部署配置。

## 新增目录

```text
server/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
  scripts/
  README.md
  requirements.txt
  Dockerfile

deploy/
  docker-compose.yml
```

## 插件侧流程

### 本地直连模式

```text
插件收集 prompt + FreeCAD context
  -> 构造 prompt messages
  -> 调用 OpenAI-compatible /chat/completions
  -> 解析 JSON
  -> 本地 AST 校验
  -> 展示脚本
  -> 本地 FreeCAD 执行和渲染
```

### 云端 SaaS 模式

```text
插件收集 prompt + FreeCAD context
  -> 调用 SaaS /api/v1/plugin/generate
  -> 云端编排 Prompt 并调用 LLM
  -> 云端保存任务和脚本
  -> 插件收到 summary / parameters / script
  -> 插件本地 AST 校验
  -> 展示脚本
  -> 本地 FreeCAD 执行和渲染
  -> 插件回传执行结果
```

## 云端 API

当前已实现插件端 API：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 后端健康检查 |
| GET | `/api/v1/plugin/health` | 插件 API 健康检查 |
| POST | `/api/v1/plugin/auth/verify` | 校验插件 API Key |
| POST | `/api/v1/plugin/generate` | 生成 FreeCAD Python 脚本 |
| POST | `/api/v1/plugin/repair` | 修复失败脚本 |
| POST | `/api/v1/plugin/regenerate` | 按参数重新生成 |
| POST | `/api/v1/plugin/execution-reports` | 回传执行结果 |

## MySQL 数据表

当前后端模型包括：

- `workspaces`
- `api_keys`
- `projects`
- `templates`
- `generation_tasks`
- `generated_scripts`
- `execution_reports`
- `usage_records`

阶段 4 原型启动时会通过 SQLAlchemy `create_all` 自动建表。

## 启动方式

### Docker Compose

```powershell
cd deploy
docker compose up --build
```

默认云端连接信息：

```text
SaaS Base URL: http://127.0.0.1:8000
SaaS API Key: dev-plugin-key
```

### 本地 Python

参考：

```text
server/README.md
```

## 限制

- Web 管理后台尚未实现页面，只完成了 SaaS 后端和插件接入主链路。
- 阶段 4 仍然在本地 FreeCAD 中执行和渲染模型，云端不运行 FreeCAD。
- 云端模板库数据表已预留，插件模板仍以内置模板为主。
- API Key 生产级创建、轮换和管理页面尚未实现。
- token 用量表已预留，当前尚未从不同模型供应商解析真实 token 账单。

## 下一步建议

- 增加 Web 管理后台：任务历史、模板管理、API Key 管理、用量统计。
- 增加 Alembic 迁移，替代原型阶段的 `create_all`。
- 增加云端模板拉取接口，并让插件启动时同步模板。
- 增加 SaaS 登录、Workspace 成员和权限管理。
- 增加任务列表和详情查询 API。
