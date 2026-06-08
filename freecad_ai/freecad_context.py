"""Collect a compact context summary from the active FreeCAD document."""

import FreeCAD as App
import FreeCADGui as Gui


def _shape_summary(obj):
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return ""
    try:
        box = shape.BoundBox
        return "bbox=({:.2f},{:.2f},{:.2f})".format(box.XLength, box.YLength, box.ZLength)
    except Exception:
        return ""


def _placement_summary(obj):
    try:
        placement = obj.Placement
        base = placement.Base
        return "placement=({:.2f},{:.2f},{:.2f})".format(base.x, base.y, base.z)
    except Exception:
        return ""


def _property_summary(obj):
    parts = []
    for prop in ("Length", "Width", "Height", "Radius", "Diameter"):
        try:
            if hasattr(obj, prop):
                value = getattr(obj, prop)
                parts.append("{}={}".format(prop, value))
        except Exception:
            continue
    return ", ".join(parts)


def collect_context():
    doc = App.ActiveDocument
    if doc is None:
        return "No active document."

    lines = ["Document: {}".format(doc.Name)]

    try:
        selection = Gui.Selection.getSelection()
    except Exception:
        selection = []
    if selection:
        lines.append("Selected objects: " + ", ".join(obj.Name for obj in selection))
        lines.append("Selected object details:")
        for obj in selection[:10]:
            selected_item = "- name={}, label={}, type={}".format(obj.Name, obj.Label, obj.TypeId)
            shape_summary = _shape_summary(obj)
            placement_summary = _placement_summary(obj)
            property_summary = _property_summary(obj)
            extras = [part for part in (shape_summary, placement_summary, property_summary) if part]
            if extras:
                selected_item += ", " + ", ".join(extras)
            lines.append(selected_item)
    else:
        lines.append("Selected objects: none")

    if not doc.Objects:
        lines.append("Objects: none")
        return "\n".join(lines)

    lines.append("Objects:")
    for obj in doc.Objects[:30]:
        summary = _shape_summary(obj)
        placement = _placement_summary(obj)
        props = _property_summary(obj)
        item = "- name={}, label={}, type={}".format(obj.Name, obj.Label, obj.TypeId)
        extras = [part for part in (summary, placement, props) if part]
        if extras:
            item += ", " + ", ".join(extras)
        lines.append(item)
    if len(doc.Objects) > 30:
        lines.append("- ... {} more objects".format(len(doc.Objects) - 30))
    return "\n".join(lines)
