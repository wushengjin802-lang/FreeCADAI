"""AST-based safety checks for generated FreeCAD Python scripts."""

import ast


FORBIDDEN_MODULES = {
    "builtins",
    "ctypes",
    "importlib",
    "inspect",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}

ALLOWED_MODULES = {
    "FreeCAD",
    "FreeCADGui",
    "Part",
    "PartGui",
    "Draft",
    "Sketcher",
    "SketcherGui",
    "math",
}

FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
    "vars",
}

FORBIDDEN_ATTRIBUTES = {
    "Popen",
    "call",
    "copyfile",
    "copytree",
    "dump",
    "dumps",
    "load",
    "loads",
    "open",
    "popen",
    "remove",
    "removedirs",
    "rename",
    "replace",
    "request",
    "rmdir",
    "rmtree",
    "run",
    "send",
    "system",
    "unlink",
    "urlopen",
    "write",
}


class ScriptValidationError(ValueError):
    pass


def _root_module(name):
    return name.split(".", 1)[0]


def validate_script(script):
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        raise ScriptValidationError("Python syntax error: {}".format(exc))

    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_module(alias.name)
                if root in FORBIDDEN_MODULES or root not in ALLOWED_MODULES:
                    errors.append("Import not allowed: {}".format(alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = _root_module(module)
            if root in FORBIDDEN_MODULES or root not in ALLOWED_MODULES:
                errors.append("Import-from not allowed: {}".format(module))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                errors.append("Call not allowed: {}".format(func.id))
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRIBUTES:
                errors.append("Attribute call not allowed: {}".format(func.attr))

    if errors:
        raise ScriptValidationError("\n".join(sorted(set(errors))))
    return True
