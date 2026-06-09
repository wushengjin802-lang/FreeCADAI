# FreeCADAI

FreeCADAI 是面向 FreeCAD 的 AI 智能工作台插件，并配套 FastAPI + MySQL + Redis + Next.js 的 SaaS 管理后台。

当前核心能力：

- FreeCAD 插件内通过自然语言生成、修复、重生成 FreeCAD Python 脚本。
- 支持本地直连 LLM 和云端 SaaS 两种服务模式。
- 支持三维实体、二维草图、常用模板、参数 JSON 编辑和自动安全校验。
- 云端 SaaS 支持工作区、模板、API Key、任务历史、用量统计、套餐限制和异步任务队列。
- 管理后台使用 Next.js + TypeScript + Ant Design + Query/Zustand/ECharts。

## 目录结构

```text
freecad_ai/   FreeCAD 插件代码
server/       FastAPI SaaS 后端
web/          Next.js 管理后台
deploy/       Docker Compose 部署配置
scripts/      本地辅助脚本
docs/         阶段说明和技术文档
```

## FreeCAD 插件安装

将项目同步到 FreeCAD 的 `Mod` 插件目录后重启 FreeCAD。

本机当前插件目录：

```text
C:\Program Files\FreeCAD 1.1\Mod\FreeCADAI
```

同步命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_to_freecad_mod.ps1
```

用户级插件目录也可使用：

```text
%APPDATA%\FreeCAD\Mod\FreeCADAI
```

重启 FreeCAD 后，在工作台列表中选择 `FreeCADAI`。AI 面板会自动打开，也可以通过 `FreeCADAI` 菜单或工具栏打开。

## 插件配置

### 本地直连 LLM

在插件 `设置` 页选择 `本地直连 LLM`，填写：

```text
Base URL    兼容 OpenAI /chat/completions 的地址，例如 https://api.openai.com/v1
API Key     模型服务 API Key
Model       模型名称
Temperature 建议 0.0 到 0.2
```

### 云端 SaaS 服务

在插件 `设置` 页选择 `云端 SaaS 服务`。

推荐流程：

1. 填写 `SaaS Base URL`。
2. 输入云端账号用户名和密码，点击 `1 登录账号`。
3. 点击 `2 刷新工作区`。
4. 选择工作区，点击 `3 绑定并生成 Key`。
5. 点击 `4 检查连接`。
6. 保存设置。

本地 SaaS 示例：

```text
SaaS Base URL: http://127.0.0.1:8000
```

线上 SaaS 示例：

```text
SaaS Base URL: http://119.29.16.170/freecadai
```

## Docker 本地部署

本地部署使用 `deploy/docker-compose.yml`，包含：

- `mysql`：业务数据库
- `redis`：任务队列和缓存
- `api`：FastAPI 后端
- `worker`：异步 LLM 任务 Worker
- `web`：Next.js 管理后台

启动：

```powershell
cd deploy
docker compose up -d --build
```

查看状态：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
```

停止：

```powershell
docker compose down
```

本地访问：

```text
API 健康检查: http://127.0.0.1:8000/health
API 文档:     http://127.0.0.1:8000/docs
管理后台:    http://127.0.0.1:3000/admin
```

## Docker 生产部署

当前线上部署信息：

```text
服务器: 119.29.16.170
部署目录: /home/app/freecadai
管理后台: http://119.29.16.170/freecadai/admin
插件 SaaS Base URL: http://119.29.16.170/freecadai
```

推荐生产启动命令：

```bash
cd /home/app/freecadai
docker compose -f docker-compose.prod.yml up -d --build
```

生产环境镜像 build、启动、重启和排查命令：

```bash
# 进入部署目录
cd /home/app/freecadai

# 构建生产镜像
docker compose -f docker-compose.prod.yml build

# 构建并后台启动服务
docker compose -f docker-compose.prod.yml up -d --build

# 查看容器运行状态
docker compose -f docker-compose.prod.yml ps
docker ps --filter name=freecadai

# 查看 API 容器日志
docker logs -f --tail=100 freecadai-api

# 重启 API 容器
docker compose -f docker-compose.prod.yml restart api

# 停止生产服务
docker compose -f docker-compose.prod.yml down
```

当前线上容器信息：

```text
容器名：freecadai-api
镜像名：freecadai-api
部署目录：/home/app/freecadai
启动方式：docker compose -f docker-compose.prod.yml up -d --build
重启策略：unless-stopped
```

如果生产环境直接使用 `deploy/docker-compose.yml`，则命令为：

```bash
cd /home/app/freecadai/deploy
docker compose up -d --build
```

生产环境必须确认以下服务都正常：

```bash
docker ps
docker logs --tail=100 freecadai-api
docker logs --tail=100 freecadai-worker
docker logs --tail=100 freecadai-web
docker logs --tail=100 freecadai-redis
docker logs --tail=100 freecadai-mysql
```

阶段 14 后必须启动 `freecadai-worker`，否则插件提交的异步生成任务会停留在 `queued`。

## 生产环境变量

后端关键环境变量：

```text
FREECADAI_DATABASE_URL      MySQL 连接串
FREECADAI_REDIS_URL         Redis 连接串
FREECADAI_LLM_BASE_URL      LLM 服务地址
FREECADAI_LLM_API_KEY       LLM API Key
FREECADAI_LLM_MODEL         LLM 模型名称
FREECADAI_LLM_TEMPERATURE   温度参数
FREECADAI_ADMIN_USERNAME    默认管理员用户名
FREECADAI_ADMIN_PASSWORD    默认管理员密码，当前默认值 admin@123，仅首次初始化使用
FREECADAI_AUTO_MIGRATE      是否启动时自动迁移，默认 1
```

不要把真实密码、真实 API Key 写入 README。生产环境应放在服务器 `.env`、Compose 环境变量或密钥管理系统中。

## 管理后台

访问地址：

```text
http://119.29.16.170/freecadai/admin
```

登录方式：

```text
管理员用户名 + 管理员密码
```

后台主要功能：

- 工作区管理
- 任务历史和任务详情
- 云端模板管理
- 插件 API Key 管理
- 用量统计、Token 和成本统计
- 套餐限制和超限提示
- 管理员账号和审计日志
- 异步任务取消和重试

## 常用运维命令

数据库迁移：

```bash
python -m alembic -c server/alembic.ini upgrade head
```

后端本地编译检查：

```powershell
python -m compileall server freecad_ai
```

前端构建：

```powershell
cd web
npm run build
```

查看 Docker 容器：

```bash
docker ps
```

重启服务：

```bash
docker restart freecadai-api freecadai-worker freecadai-web
```

## 关键 API

插件 API：

```text
POST /api/v1/plugin/auth/verify
GET  /api/v1/plugin/templates
POST /api/v1/plugin/generate/submit
POST /api/v1/plugin/repair/submit
POST /api/v1/plugin/regenerate/submit
GET  /api/v1/plugin/tasks/{task_id}
POST /api/v1/plugin/tasks/{task_id}/cancel
POST /api/v1/plugin/tasks/{task_id}/retry
POST /api/v1/plugin/execution-reports
```

管理 API：

```text
POST /api/v1/admin/auth/login
GET  /api/v1/admin/workspaces
GET  /api/v1/admin/tasks
GET  /api/v1/admin/templates
GET  /api/v1/admin/api-keys
GET  /api/v1/admin/usage
GET  /api/v1/admin/usage/by-model
GET  /api/v1/admin/billing/summary
GET  /api/v1/admin/audit-logs
```

## 本地数据位置

插件会在 FreeCAD 用户数据目录下创建 `FreeCADAI` 文件夹，用于保存：

```text
config.json   插件配置
history.jsonl 本地生成和执行历史
```

## 故障排查

如果插件云端任务一直处于 `queued`：

- 检查 `freecadai-worker` 是否运行。
- 检查 Redis 连接是否正常。
- 查看 `freecadai-worker` 日志。

如果管理后台无法访问：

- 检查 `freecadai-web` 是否运行。
- 检查反向代理路径 `/freecadai/admin`。
- 检查 API `/health` 是否正常。

如果 LLM 返回 401/403：

- 检查 `FREECADAI_LLM_API_KEY`。
- 检查模型服务账号额度和权限。

如果 LLM 返回 429 或 `insufficient_quota`：

- 当前模型服务账号额度不足或账单不可用。
- 需要到服务商控制台检查余额、套餐、项目额度，或更换可用 API Key。

如果 HTTPS/SSL 连接异常：

- OpenAI 官方地址应为 `https://api.openai.com/v1`。
- 本地或私有网关如果只支持 HTTP，不要误填 HTTPS。
- 检查代理、VPN、公司网络或安全软件是否拦截 TLS。

## 阶段文档

阶段实现说明保存在 `docs/`：

```text
docs/phase-13-implementation.md
docs/phase-14-implementation.md
```
