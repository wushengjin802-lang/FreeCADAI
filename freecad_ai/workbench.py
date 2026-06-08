"""FreeCADAI workbench definition."""

import traceback

import FreeCAD as App
import FreeCADGui as Gui

from freecad_ai.commands import register_commands


class FreeCADAIWorkbench(Gui.Workbench):
    MenuText = "FreeCADAI"
    ToolTip = "AI-assisted 3D modeling workbench prototype."
    Icon = ""

    def Initialize(self):
        register_commands()
        commands = ["FreeCADAI_ShowPanel", "FreeCADAI_CreateDemoModel"]
        self.appendToolbar("FreeCADAI", commands)
        self.appendMenu("FreeCADAI", commands)

    def Activated(self):
        try:
            from freecad_ai.ui.ai_panel import show_ai_panel

            show_ai_panel()
        except Exception:
            App.Console.PrintError("FreeCADAI panel failed to open.\n")
            App.Console.PrintError(traceback.format_exc())

    def Deactivated(self):
        return

    def GetClassName(self):
        return "Gui::PythonWorkbench"
