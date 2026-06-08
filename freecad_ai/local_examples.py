"""Local example payloads for testing without an LLM API key."""


BASE_PLATE_SCRIPT = """import FreeCAD as App
import FreeCADGui as Gui
import Part

doc = App.ActiveDocument
if doc is None:
    doc = App.newDocument("FreeCADAI_Local_Example")

length = 100.0
width = 60.0
height = 10.0
hole_diameter = 8.0
edge_offset = 12.0

base = Part.makeBox(length, width, height)
hole_radius = hole_diameter / 2.0

shape = base
for x in (edge_offset, length - edge_offset):
    for y in (edge_offset, width - edge_offset):
        center = App.Vector(x, y, -1.0)
        direction = App.Vector(0, 0, 1)
        hole = Part.makeCylinder(hole_radius, height + 2.0, center, direction)
        shape = shape.cut(hole)

obj = doc.addObject("Part::Feature", "FreeCADAI_Local_BasePlate")
obj.Label = "FreeCADAI 本地示例底板"
obj.Shape = shape

doc.recompute()
try:
    Gui.ActiveDocument.ActiveView.fitAll()
except Exception:
    pass
"""


def build_local_example_payload(prompt):
    return {
        "summary": "本地示例：创建一个带四个安装孔的矩形底板",
        "parameters": {
            "length": 100,
            "width": 60,
            "height": 10,
            "hole_diameter": 8,
            "edge_offset": 12,
        },
        "script": BASE_PLATE_SCRIPT,
        "expected_objects": ["FreeCADAI_Local_BasePlate"],
        "notes": [
            "这是无需 LLM API 的本地示例脚本。",
            "用于验证脚本预览、安全校验和 FreeCAD 执行链路。",
            "用户原始需求：{}".format(prompt or "未填写"),
        ],
    }
