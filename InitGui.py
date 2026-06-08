"""GUI initialization for the FreeCADAI workbench."""

import FreeCADGui as Gui

from freecad_ai.workbench import FreeCADAIWorkbench


Gui.addWorkbench(FreeCADAIWorkbench())

