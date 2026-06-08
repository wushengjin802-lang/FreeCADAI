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

## 插件配置

在 FreeCADAI 插件的 `设置` 页：

- 服务模式：`云端 SaaS 服务`
- SaaS Base URL：`http://127.0.0.1:8000`
- SaaS API Key：`dev-plugin-key`
- Project ID：可留空
- 云端同步：勾选

保存后回到 `生成` 页，即可通过云端服务生成脚本。脚本仍在本地 FreeCAD 中执行和渲染。
