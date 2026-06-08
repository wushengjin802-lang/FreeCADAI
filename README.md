# FreeCADAI

FreeCADAI 是一个面向 FreeCAD 的 AI 智能工作台原型插件。当前版本已实现阶段 4 原型：文本需求输入、三维实体/二维草图模式、常用模板、本地直连 LLM 或云端 SaaS 服务、JSON 脚本生成、安全校验、脚本预览、参数 JSON 编辑、自动修复循环、在当前 FreeCAD 文档中执行脚本、本地历史记录，以及 FastAPI + MySQL SaaS 后端骨架。

## 当前功能

- 注册 `FreeCADAI` 工作台。
- 在 FreeCAD 内打开独立的可停靠 AI 面板，面板中的每个功能区域都有中文标题说明。
- 支持兼容 OpenAI `/chat/completions` 的大模型 API。
- 支持 `本地直连 LLM` 和 `云端 SaaS 服务` 两种服务模式。
- 云端 SaaS 模式支持生成、修复、参数重生成和执行结果回传。
- 在 FreeCAD 用户数据目录下保存本地 API 配置。
- 从当前 FreeCAD 文档和选中对象中采集上下文。
- 针对选中对象采集名称、类型、包围盒、位置和常见尺寸属性，支持“修改当前模型”的提示。
- 支持 `三维实体` 和 `二维草图` 两种建模模式。
- 提供常用建模模板，例如四孔底板、U32 AI 算力机架、法兰盘、L 型支架、角码、轴承座、联轴器、齿轮、同步带轮、散热片、电控盒、导轨滑块、风扇支架、脚轮底座、钣金盒、支撑柱和修改选中对象。
- 提供二维草图模板，例如矩形孔板、法兰盘、轴类截面、钣金展开和 U16 机架正视图。
- 要求 LLM 返回包含 `summary`、`parameters`、`script`、`expected_objects`、`notes` 的 JSON 对象。
- 在执行前展示生成的 FreeCAD Python 脚本。
- 展示并允许编辑 `parameters` JSON，可按编辑后的参数重新生成脚本。
- 生成、修复、参数重生成和执行时会自动进行 AST 基础安全检查，无需手动点击校验按钮。
- LLM 生成、修复和参数重生成在后台线程运行，避免网络请求期间卡住 FreeCAD 主界面。
- 在当前 FreeCAD 文档中执行校验后的脚本并刷新视图。
- 执行完成后会显示新增对象名称和对象数量，方便对照模型树检查是否真的生成。
- 执行失败时保留失败脚本和错误信息，可点击 `调用 LLM 修复脚本` 生成修正版。
- 支持执行失败后自动调用 LLM 修复并重试，最多 3 次。
- 使用 JSONL 保存本地生成和执行历史。
- 提供 `本地示例脚本`，在没有 API Key 或额度不足时也能测试脚本预览、校验和执行链路。

## 手动安装

将当前项目目录复制或链接到 FreeCAD 的 `Mod` 插件目录，然后重启 FreeCAD。

本机当前使用的插件目录：

```text
C:\Program Files\FreeCAD 1.1\Mod\FreeCADAI
```

常见用户级插件目录：

```text
%APPDATA%\FreeCAD\Mod\FreeCADAI
```

重启 FreeCAD 后，在工作台列表中选择 `FreeCADAI`。AI 面板会自动打开，也可以通过 `FreeCADAI` 菜单或工具栏打开。

## 阶段 4 插件测试流程

1. 启动 FreeCAD。
2. 选择 `FreeCADAI` 工作台。
3. 打开 AI 面板中的 `设置` 标签页。
4. 选择 `服务模式`。
5. 如果使用 `本地直连 LLM`，填写 `Base URL`、`API Key`、`Model` 和 `Temperature`。
6. 如果使用 `云端 SaaS 服务`，填写 `SaaS Base URL`、`SaaS API Key` 和 `Project ID`。
7. 回到 `生成` 标签页。
8. 选择 `建模模式`：常规建模选 `三维实体`，只需要 Sketcher/Draft 轮廓时选 `二维草图`。
9. 输入建模需求，或在 `常用模板` 中选择一个模板并点击 `套用模板`。

```text
创建一个 100 x 60 x 10 mm 的底板，并在四角添加直径 8 mm 的安装孔。
```

10. 点击 `调用 LLM 生成脚本`。
11. 检查生成的脚本预览。
12. 检查或修改 `参数 JSON 编辑` 区域。
13. 如修改了参数，点击 `按参数重新生成`。
14. 勾选 `执行失败时自动修复`，设置最多修复次数。
15. 点击 `执行脚本`，插件会自动校验脚本，通过后再执行。
16. 确认当前 FreeCAD 文档中生成了 3D 模型或二维草图。
17. 如果自动修复仍失败，可点击 `调用 LLM 修复脚本` 手动再修复一次。
18. 打开 `历史` 标签页，确认生成、修复、自动修复、执行记录已保存。

## 阶段 4 SaaS 后端

阶段 4 新增 `server/` 和 `deploy/`：

- `server/`：FastAPI + SQLAlchemy + MySQL SaaS 后端原型。
- `deploy/docker-compose.yml`：MySQL + API 的本地容器启动配置。

本地启动说明见：

```text
server/README.md
```

插件云端模式默认可以连接：

```text
SaaS Base URL: http://127.0.0.1:8000
SaaS API Key: dev-plugin-key
```

当前服务器 Docker 部署信息：

```text
容器名：freecadai-api
镜像名：freecadai-api
部署目录：/home/app/freecadai
启动方式：docker compose -f docker-compose.prod.yml up -d --build
重启策略：unless-stopped
```

## 二维草图

如果要生成二维草图：

1. 在 `建模模式` 中选择 `二维草图`。
2. 输入需求，例如：

```text
生成一个二维 Sketcher 草图，不要生成三维实体。草图位于 XY 平面，创建一个 100 x 60 mm 的矩形轮廓，并在四角添加直径 8 mm 的圆孔。
```

3. 或选择 `二维草图：矩形孔板`、`二维草图：法兰盘` 等模板。
4. 点击 `调用 LLM 生成脚本`。
5. 执行脚本后，FreeCAD 文档中会创建 Sketcher 或 Draft 二维对象。

## 修改当前模型

如果要让 AI 修改已有模型：

1. 在 FreeCAD 视图或模型树中选中目标对象。
2. 在建模需求中明确描述修改，例如：

```text
在当前选中的底板中心增加一个直径 20 mm 的通孔。
```

3. 点击 `调用 LLM 生成脚本`。
4. 插件会把选中对象名称、类型、包围盒、位置等上下文发给 LLM。
5. 检查脚本是否使用了上下文中的真实对象名，再执行。

## 无 API Key 测试方式

如果暂时没有 API Key，可以使用以下方式验证本地插件链路：

- 点击 `本地示例脚本`，先生成一段无需 API 的脚本，再点击 `执行脚本`。
- 手动粘贴一段 FreeCAD Python 脚本到脚本预览区，然后点击 `执行脚本`；插件会自动校验，通过后再执行。

如果看到 `LLM HTTP 429` 或 `insufficient_quota`，说明当前 API Key 对应账号额度不足或账单不可用。这不是 FreeCADAI 插件本身的错误，需要到服务商控制台检查余额、套餐、项目额度或更换可用 API Key。

如果看到 `SSL: UNEXPECTED_EOF_WHILE_READING`，说明 HTTPS/TLS 连接被中途断开。优先检查：

- OpenAI 官方 `Base URL` 是否为 `https://api.openai.com/v1`。
- 本地或私有网关是否只支持 `http://`，不要误填 `https://`。
- 代理、VPN、公司网络或安全软件是否拦截了 TLS。
- 当前地址是否真的兼容 OpenAI `/chat/completions`。

## API 配置说明

`Base URL` 应填写兼容 OpenAI Chat Completions 的服务地址，例如：

```text
https://api.openai.com/v1
```

也可以填写 DeepSeek、通义千问、私有模型网关等兼容 `/chat/completions` 的地址。

`Model` 填写服务商提供的模型名称。

`Temperature` 建议先设置为 `0.0` 到 `0.2`，这样生成的建模脚本更稳定。

## 本地数据位置

插件会在 FreeCAD 用户数据目录下创建 `FreeCADAI` 文件夹，用于保存：

- `config.json`：API 配置。
- `history.jsonl`：生成和执行历史。

## 开发同步

开发目录中的内容可以通过以下脚本同步到 FreeCAD 插件目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_to_freecad_mod.ps1
```

默认同步目标：

```text
C:\Program Files\FreeCAD 1.1\Mod\FreeCADAI
```

## 下一阶段

阶段 5 建议继续实现：

- 更严格的结构化建模 DSL，逐步减少直接执行任意 Python 的风险。
- 更完整的模板库和参数表单。
- Web 管理后台：任务历史、模板管理、API Key 管理和用量统计。
- 云端模板库同步。
