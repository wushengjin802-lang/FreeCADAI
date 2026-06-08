"""FreeCAD command registrations for the phase 0 prototype."""

import traceback

import FreeCAD as App
import FreeCADGui as Gui

from freecad_ai.freecad_ops import create_phase0_demo_model
from freecad_ai.ui.ai_panel import show_ai_panel


class ShowAIPanelCommand:
    """Show the dockable AI panel."""

    def GetResources(self):
        return {
            "MenuText": "Show AI Panel",
            "ToolTip": "Open the FreeCADAI dock panel.",
            "Pixmap": "",
        }

    def Activated(self):
        show_ai_panel()

    def IsActive(self):
        return True


class CreateDemoModelCommand:
    """Create a deterministic test model in the active FreeCAD document."""

    def GetResources(self):
        return {
            "MenuText": "Create Demo Model",
            "ToolTip": "Create a simple base plate with four mounting holes.",
            "Pixmap": "",
        }

    def Activated(self):
        try:
            create_phase0_demo_model()
        except Exception:
            App.Console.PrintError("FreeCADAI demo model failed:\n")
            App.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return True


def register_commands():
    Gui.addCommand("FreeCADAI_ShowPanel", ShowAIPanelCommand())
    Gui.addCommand("FreeCADAI_CreateDemoModel", CreateDemoModelCommand())

