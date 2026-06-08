"""Execute validated FreeCAD Python scripts."""

import math

import FreeCAD as App
import FreeCADGui as Gui
import Part

try:
    import PartGui
except ImportError:
    PartGui = None

try:
    import Draft
except ImportError:
    Draft = None

try:
    import Sketcher
except ImportError:
    Sketcher = None

try:
    import SketcherGui
except ImportError:
    SketcherGui = None

from freecad_ai.validator import validate_script


ALLOWED_IMPORTS = {
    "FreeCAD": App,
    "FreeCADGui": Gui,
    "Part": Part,
    "PartGui": PartGui,
    "Draft": Draft,
    "Sketcher": Sketcher,
    "SketcherGui": SketcherGui,
    "math": math,
}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".", 1)[0]
    if level != 0 or root not in ALLOWED_IMPORTS or ALLOWED_IMPORTS[root] is None:
        raise ImportError("Import not allowed: {}".format(name))
    return ALLOWED_IMPORTS[root]


SAFE_BUILTINS = {
    "__import__": _safe_import,
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "Exception": Exception,
    "float": float,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "object": object,
    "range": range,
    "round": round,
    "set": set,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def _object_names(doc):
    if doc is None:
        return []
    return [obj.Name for obj in doc.Objects]


def _show_objects(doc, names):
    if doc is None:
        return
    for name in names:
        obj = doc.getObject(name)
        if obj is None:
            continue
        try:
            obj.ViewObject.Visibility = True
        except Exception:
            pass


def _refresh_view(doc, view_mode):
    try:
        gui_doc = Gui.getDocument(doc.Name) if doc is not None else Gui.ActiveDocument
        view = gui_doc.ActiveView if gui_doc is not None else Gui.ActiveDocument.ActiveView
        if view_mode == "2d_sketch":
            try:
                view.viewTop()
            except Exception:
                pass
        else:
            try:
                view.viewAxonometric()
            except Exception:
                pass
        view.fitAll()
    except Exception:
        pass


def execute_script(script, view_mode="3d_solid"):
    validate_script(script)
    before_doc = App.ActiveDocument
    before_names = set(_object_names(before_doc))
    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "App": App,
        "Gui": Gui,
        "Part": Part,
        "PartGui": PartGui,
        "Draft": Draft,
        "Sketcher": Sketcher,
        "SketcherGui": SketcherGui,
        "math": math,
    }
    exec(compile(script, "<FreeCADAI generated script>", "exec"), namespace, namespace)
    doc = App.ActiveDocument
    if doc is not None:
        doc.recompute()
    after_names = _object_names(doc)
    new_names = [name for name in after_names if name not in before_names]
    visible_names = new_names or after_names
    _show_objects(doc, visible_names)
    if doc is not None:
        doc.recompute()
    _refresh_view(doc, view_mode)
    if doc is None or not after_names:
        raise RuntimeError("脚本执行完成，但当前 FreeCAD 文档中没有检测到任何对象。")
    return {
        "document": doc.Name,
        "new_objects": new_names,
        "object_count": len(after_names),
        "visible_objects": visible_names,
    }
