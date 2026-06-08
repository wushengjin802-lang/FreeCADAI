# FreeCADAI SaaS 后端原型

这是阶段 4 的 FastAPI + MySQL SaaS 后端原型，用于把 FreeCAD 插件从本地直连 LLM 扩展为可选的云端 AI 编排服务。

## 能力

- 插件 API Key 鉴权。
- 生成 FreeCAD Python 脚本。
- 修复失败脚本。
- 按参数重新生成脚本。
- 保存生成任务和脚本。
- 接收插件执行结果回传。
- 使用 MySQL 8.x 保存 SaaS 任务数据。
- 使用 Redis 做缓存/健康检查基础设施。
- 提供阶段 5 管理 API：任务历史、任务详情、模板管理、API Key 创建、用量统计。

## 本地启动

1. 安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
```

2. 准备 MySQL：

```sql
source server/scripts/init_mysql.sql;
```

3. 复制配置：

```powershell
Copy-Item server\.env.example server\.env
```

4. 修改 `server\.env`：

```text
FREECADAI_LLM_API_KEY=你的模型服务 Key
FREECADAI_ADMIN_TOKEN=你的管理端 Token
```

5. 启动 API：

```powershell
uvicorn server.app.main:app --host 127.0.0.1 --port 8000 --reload
```

6. 健康检查：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

## Docker Compose 启动

```powershell
cd deploy
docker compose up --build
```

默认插件 API Key：

```text
dev-plugin-key
```

默认管理端 Token：

```text
dev-admin-token
```

## 插件配置

在 FreeCADAI 插件的 `设置` 页：

- 服务模式：`云端 SaaS 服务`
- SaaS Base URL：`http://127.0.0.1:8000`
- SaaS API Key：`dev-plugin-key`
- Project ID：可留空
- 云端同步：勾选

保存后回到 `生成` 页，即可通过云端服务生成脚本。脚本仍在本地 FreeCAD 中执行和渲染。

## 阶段 5 管理 API

管理 API 使用：

```http
Authorization: Bearer <FREECADAI_ADMIN_TOKEN>
```

已实现接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/admin/tasks` | 查询任务历史 |
| GET | `/api/v1/admin/tasks/{task_id}` | 查询任务详情 |
| GET | `/api/v1/admin/templates` | 查询模板 |
| POST | `/api/v1/admin/templates` | 新增模板 |
| PUT | `/api/v1/admin/templates/{template_id}` | 修改模板 |
| DELETE | `/api/v1/admin/templates/{template_id}` | 删除模板 |
| POST | `/api/v1/admin/api-keys` | 创建插件 API Key |
| GET | `/api/v1/admin/usage` | 查看用量摘要 |

插件模板同步接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/plugin/templates` | 插件拉取云端模板 |

## 阶段 10 数据库迁移

阶段 10 开始，后端使用 Alembic 管理数据库结构。

常用命令：

```powershell
python -m alembic -c server/alembic.ini upgrade head
python -m alembic -c server/alembic.ini current
python -m alembic -c server/alembic.ini history
```

应用启动时默认会自动执行迁移：

```text
FREECADAI_AUTO_MIGRATE=1
```

如果生产环境希望手动控制迁移，可以关闭自动迁移：

```text
FREECADAI_AUTO_MIGRATE=0
```

已有线上库如果已经存在业务表但没有 `alembic_version`，应用会先执行 `stamp head`，把当前结构标记为基线版本，避免重复建表。
