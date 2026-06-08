"""Small FreeCAD operations used by the phase 0 prototype."""

import FreeCAD as App
import FreeCADGui as Gui
import Part


def ensure_document():
    """Return the active document, creating one if needed."""
    doc = App.ActiveDocument
    if doc is None:
        doc = App.newDocument("FreeCADAI_Demo")
    return doc


def create_phase0_demo_model():
    """Create a base plate with four mounting holes in the active document."""
    doc = ensure_document()

    length = 100.0
    width = 60.0
    height = 10.0
    hole_diameter = 8.0
    edge_offset = 12.0

    base = Part.makeBox(length, width, height)
    hole_radius = hole_diameter / 2.0
    holes = []

    for x in (edge_offset, length - edge_offset):
        for y in (edge_offset, width - edge_offset):
            center = App.Vector(x, y, -1.0)
            direction = App.Vector(0, 0, 1)
            holes.append(Part.makeCylinder(hole_radius, height + 2.0, center, direction))

    shape = base
    for hole in holes:
        shape = shape.cut(hole)

    obj = doc.addObject("Part::Feature", "FreeCADAI_Phase0_BasePlate")
    obj.Shape = shape
    obj.Label = "FreeCADAI Phase 0 Base Plate"

    doc.recompute()
    Gui.ActiveDocument.ActiveView.fitAll()
    App.Console.PrintMessage("FreeCADAI phase 0 demo model created.\n")
    return obj

