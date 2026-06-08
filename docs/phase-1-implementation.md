# 阶段 1 实现说明

## 已实现内容

阶段 1 已在阶段 0 插件骨架上完成文本到 FreeCAD Python 脚本的基础闭环。

已完成：

- LLM API 配置：Base URL、API Key、Model、Temperature。
- OpenAI-compatible `/chat/completions` 调用。
- 当前 FreeCAD 文档上下文采集。
- Prompt 模板和 JSON 输出协议。
- LLM JSON 响应解析。
- 脚本预览。
- AST 基础安全校验。
- 受限执行器执行 FreeCAD Python 脚本。
- 本地 JSONL 历史记录。
- 提供本地示例脚本按钮，方便无 API Key 时测试脚本预览、校验和执行链路。

## 新增模块

```text
freecad_ai/
  executor.py
  freecad_context.py
  validator.py
  llm/
    client.py
    prompts.py
    schemas.py
  storage/
    config.py
    history.py
```

## UI 流程

```text
用户输入建模需求
  -> 插件采集当前 FreeCAD 上下文
  -> 构造 LLM prompt
  -> 调用 OpenAI-compatible LLM API
  -> 解析 JSON
  -> 展示 summary / parameters / script
  -> AST 安全校验
  -> 用户点击执行
  -> 在当前 FreeCAD 文档中渲染模型
  -> 写入历史记录
```

## LLM 输出协议

插件要求 LLM 返回一个 JSON 对象：

```json
{
  "summary": "创建一个带四个安装孔的矩形底板",
  "parameters": {
    "length": 100,
    "width": 60,
    "height": 10,
    "hole_diameter": 8
  },
  "script": "import FreeCAD as App\nimport FreeCADGui as Gui\nimport Part\n...",
  "expected_objects": ["BasePlate"],
  "notes": ["单位为 mm"]
}
```

## API 配置

在插件面板的 `设置` 页填写：

- `Base URL`：例如 `https://api.openai.com/v1`，或其他兼容 OpenAI Chat Completions 的服务。
- `API Key`：服务商 API Key。
- `Model`：模型名称。
- `Temperature`：建议 0.0 到 0.2。

配置保存到 FreeCAD 用户数据目录下的 `FreeCADAI/config.json`。

## 安全校验

当前阶段使用 Python AST 做基础检查。

禁止：

- `os`、`sys`、`subprocess`、`socket`、`shutil`、`pathlib`、`requests`、`urllib` 等模块。
- `open`、`eval`、`exec`、`compile`、`__import__` 等危险调用。
- 常见文件、网络、进程相关属性调用。

允许：

- `FreeCAD`
- `FreeCADGui`
- `Part`
- `Draft`
- `Sketcher`
- `math`

注意：这不是最终安全沙箱。阶段 2/3 建议继续收敛为白名单 DSL 或结构化建模操作协议。

## 验收步骤

1. 启动 FreeCAD。
2. 选择 `FreeCADAI` 工作台。
3. 打开右侧 `FreeCADAI` 面板。
4. 在 `设置` 页填写 LLM API 配置并保存。
5. 在 `生成` 页输入：

```text
创建一个 100 x 60 x 10 mm 的底板，并在四角添加直径 8 mm 的安装孔。
```

6. 点击 `调用 LLM 生成脚本`。
7. 确认脚本显示在预览区。
8. 点击 `校验脚本`。
9. 点击 `执行脚本`。
10. 确认当前 FreeCAD 文档中生成模型，视图自动缩放到模型。
11. 打开 `历史` 页，确认有生成或执行记录。

## 无 API Key 测试方式

如果暂时没有 API Key，可以：

- 点击 `本地示例脚本`，验证脚本预览、校验和执行链路。
- 手动粘贴 FreeCAD Python 脚本到脚本框，点击 `校验脚本` 和 `执行脚本`。

## 下一阶段建议

注意：当前阶段 2 已移除手动 `校验脚本` 按钮，改为生成、修复、参数重生成和执行时自动校验。阶段 1 文档保留的是历史实现记录。

阶段 2 建议重点实现：

- 生成失败或执行失败后的自动修复循环。
- 更强的 FreeCAD API 示例库。
- 常见零件模板。
- 参数化表单。
- 选择对象后的局部修改能力。
- 更严格的建模 DSL，降低任意 Python 执行风险。
