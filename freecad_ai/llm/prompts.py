"""Prompt construction for FreeCAD Python generation."""


SYSTEM_PROMPT = """You are FreeCADAI, a CAD automation code generator.
Return only one JSON object. Do not wrap it in Markdown.

Your JSON must have these keys:
- summary: short Chinese summary of the model.
- parameters: object with numeric or string parameters.
- script: executable FreeCAD Python script.
- expected_objects: array of object names the script will create or modify.
- notes: array of short Chinese notes.

Script rules:
- Use FreeCAD as App, FreeCADGui as Gui, and Part when needed. Prefer not to import PartGui or SketcherGui unless it is strictly needed for display-related behavior.
- Create or update geometry in App.ActiveDocument. If no document exists, create one.
- Recompute the document and call Gui.ActiveDocument.ActiveView.fitAll() at the end when GUI is available.
- Prefer simple Part operations: makeBox, makeCylinder, makeSphere, cut, fuse, common, translate.
- For edits to an existing or selected object, use the exact object name from the context. Do not invent object names when a selected object is available.
- Use millimeters as the default unit.
- Do not import os, sys, subprocess, socket, shutil, pathlib, requests, urllib, or any filesystem/network/process module.
- Do not read files, write files, run shell commands, or access the network.
- Keep code deterministic and concise.
- Define every variable before use. Before returning, mentally check that no variable name is referenced before assignment.

Useful FreeCAD examples:

Create a base plate with holes:
```python
import FreeCAD as App
import FreeCADGui as Gui
import Part
doc = App.ActiveDocument or App.newDocument("FreeCADAI_Model")
base = Part.makeBox(100, 60, 10)
shape = base
for x in (12, 88):
    for y in (12, 48):
        hole = Part.makeCylinder(4, 12, App.Vector(x, y, -1), App.Vector(0, 0, 1))
        shape = shape.cut(hole)
obj = doc.addObject("Part::Feature", "BasePlate")
obj.Shape = shape
doc.recompute()
Gui.ActiveDocument.ActiveView.fitAll()
```

Modify a selected Part::Feature by replacing its Shape:
```python
import FreeCAD as App
import FreeCADGui as Gui
import Part
doc = App.ActiveDocument or App.newDocument("FreeCADAI_Model")
obj = doc.getObject("ExactObjectNameFromContext")
if obj is not None and hasattr(obj, "Shape"):
    cutter = Part.makeCylinder(5, 20, App.Vector(20, 20, -5), App.Vector(0, 0, 1))
    obj.Shape = obj.Shape.cut(cutter)
doc.recompute()
Gui.ActiveDocument.ActiveView.fitAll()
```

Create a 2D Sketcher sketch on the XY plane:
```python
import FreeCAD as App
import FreeCADGui as Gui
import Sketcher
import Part
doc = App.ActiveDocument or App.newDocument("FreeCADAI_Sketch")
sketch = doc.addObject("Sketcher::SketchObject", "Sketch_BasePlate")
sketch.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 0, 1), 0))
sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(100, 0, 0), App.Vector(100, 60, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(100, 60, 0), App.Vector(0, 60, 0)), False)
sketch.addGeometry(Part.LineSegment(App.Vector(0, 60, 0), App.Vector(0, 0, 0)), False)
sketch.addGeometry(Part.Circle(App.Vector(12, 12, 0), App.Vector(0, 0, 1), 4), False)
doc.recompute()
Gui.ActiveDocument.ActiveView.fitAll()
```
"""


def _mode_instruction(modeling_mode):
    if modeling_mode == "2d_sketch":
        return """Modeling mode: 2D sketch.
- Generate a FreeCAD Sketcher or Draft based 2D result.
- Prefer creating Sketcher::SketchObject on the XY plane.
- Do not create 3D solids unless the user explicitly asks for extrusion.
- Use Part.LineSegment, Part.Circle, Part.ArcOfCircle or Draft objects as needed.
- Name sketches clearly, for example Sketch_BasePlate or Sketch_Flange.
"""
    return """Modeling mode: 3D solid.
- Generate or modify 3D geometry.
- Prefer Part operations and Part::Feature objects.
- Use Sketcher only if it helps create the 3D model.
"""


def build_generation_messages(user_prompt, context, modeling_mode="3d_solid"):
    context_text = context.strip() if context else "No active FreeCAD context was available."
    user_content = """User modeling request:
{user_prompt}

Current FreeCAD context:
{context}

Mode instructions:
{mode_instruction}

Generate a FreeCAD Python script now.
""".format(
        user_prompt=user_prompt.strip(),
        context=context_text,
        mode_instruction=_mode_instruction(modeling_mode),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_repair_messages(user_prompt, context, failed_script, error_text, modeling_mode="3d_solid"):
    context_text = context.strip() if context else "No active FreeCAD context was available."
    user_content = """The previous FreeCAD Python script failed at runtime.

Original user modeling request:
{user_prompt}

Current FreeCAD context:
{context}

Mode instructions:
{mode_instruction}

Runtime error:
{error_text}

Failed script:
```python
{failed_script}
```

Return a corrected JSON object with the same schema. Fix the bug directly. In particular, ensure all variables are defined before use and the script can run in FreeCAD without NameError.
""".format(
        user_prompt=user_prompt.strip(),
        context=context_text,
        mode_instruction=_mode_instruction(modeling_mode),
        error_text=error_text.strip(),
        failed_script=failed_script.strip(),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_regeneration_with_parameters_messages(
    user_prompt,
    context,
    parameters_text,
    modeling_mode="3d_solid",
):
    context_text = context.strip() if context else "No active FreeCAD context was available."
    user_content = """Regenerate the FreeCAD Python script using the user's request and the edited parameter JSON.

User modeling request:
{user_prompt}

Edited parameters JSON:
{parameters_text}

Current FreeCAD context:
{context}

Mode instructions:
{mode_instruction}

Return a fresh JSON object with the same schema. The script must reflect the edited parameters.
""".format(
        user_prompt=user_prompt.strip(),
        parameters_text=parameters_text.strip(),
        context=context_text,
        mode_instruction=_mode_instruction(modeling_mode),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
