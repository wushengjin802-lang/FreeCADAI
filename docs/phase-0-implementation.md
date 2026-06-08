# 阶段 0 实现说明

## 已实现内容

本阶段已实现 FreeCADAI 插件最小可运行骨架，用于验证 FreeCAD 插件开发链路。

已完成：

- `Init.py`：FreeCAD 模块初始化入口。
- `InitGui.py`：注册 `FreeCADAI` Workbench。
- `package.xml`：Addon 元数据。
- `freecad_ai/workbench.py`：Workbench 菜单和工具栏。
- `freecad_ai/commands.py`：命令注册。
- `freecad_ai/ui/ai_panel.py`：独立 Dock Panel。
- `freecad_ai/freecad_ops.py`：固定测试模型生成逻辑。
- `README.md`：本地安装和验证说明。

## 验证目标

阶段 0 的目标不是接入 LLM，而是确认以下链路可行：

```text
FreeCAD 加载插件
  -> 注册 FreeCADAI Workbench
  -> 打开独立 AI Dock Panel
  -> 点击按钮执行 Python 建模逻辑
  -> 在当前 FreeCAD 文档和 3D 视图中生成模型
```

## 测试模型

当前测试按钮会生成一个简单机械底板：

- 长度：100 mm
- 宽度：60 mm
- 厚度：10 mm
- 四角安装孔：直径 8 mm
- 对象名称：`FreeCADAI_Phase0_BasePlate`

## 本地安装方式

将当前项目目录复制或链接到 FreeCAD 用户插件目录。

Windows 常见路径：

```text
%APPDATA%\FreeCAD\Mod\FreeCADAI
```

重启 FreeCAD 后，切换到 `FreeCADAI` 工作台。

## 验收步骤

1. 启动 FreeCAD。
2. 在工作台列表中选择 `FreeCADAI`。
3. 确认右侧出现 `FreeCADAI` 面板。
4. 点击 `生成阶段 0 测试模型`。
5. 确认当前文档中出现带四个安装孔的底板。
6. 确认 FreeCAD 视图自动 `fitAll`。

## 下一阶段建议

阶段 1 可以在当前骨架上继续扩展：

- 增加 LLM API 配置。
- 将固定脚本替换为 LLM 生成脚本。
- 增加 JSON 输出协议。
- 增加 AST 安全检查。
- 增加脚本预览和执行确认。
