"""Real AST-based parser for Python, using the stdlib `ast` module.

This is the one language where the spec's "AST-based parsing preferred
where practical" is fully honored -- Python ships its own AST, so there's no
reason to fall back to regex here.
"""
from __future__ import annotations

import ast

from app.services.ingestion.parser.base import ExtractedImport, ExtractedSymbol, ParsedFile

_ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def parse_python(content: str) -> ParsedFile:
    result = ParsedFile()
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        result.error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports.append(ExtractedImport(raw=alias.name, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            prefix = "." * (node.level or 0)
            raw = f"{prefix}{module}"
            names = [a.name for a in node.names]
            result.imports.append(ExtractedImport(raw=raw, imported_names=names, line=node.lineno))

    _walk_definitions(tree.body, parent=None, result=result)
    return result


def _walk_definitions(body: list[ast.stmt], parent: str | None, result: ParsedFile) -> None:
    for node in body:
        if isinstance(node, ast.ClassDef):
            result.symbols.append(
                ExtractedSymbol(
                    name=node.name,
                    symbol_type="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    docstring=ast.get_docstring(node),
                    parent_name=parent,
                    signature=_class_signature(node),
                )
            )
            _walk_definitions(node.body, parent=node.name, result=result)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            route = _detect_route(node)
            symbol_type = "method" if parent else "function"
            result.symbols.append(
                ExtractedSymbol(
                    name=node.name,
                    symbol_type=symbol_type,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    docstring=ast.get_docstring(node),
                    parent_name=parent,
                    signature=_function_signature(node),
                )
            )
            if route:
                path, method = route
                result.symbols.append(
                    ExtractedSymbol(
                        name=node.name,
                        symbol_type="route",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        parent_name=parent,
                        route_path=path,
                        http_method=method,
                    )
                )
            # Do not descend into nested function bodies for now -- keeps
            # the symbol table at module/class/function granularity, which
            # is what the spec's symbol model (section 12) asks for.


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = ""
    if node.returns is not None:
        try:
            returns = f" -> {ast.unparse(node.returns)}"
        except Exception:
            returns = ""
    return f"{prefix} {node.name}({args}){returns}"


def _class_signature(node: ast.ClassDef) -> str:
    bases = []
    for b in node.bases:
        try:
            bases.append(ast.unparse(b))
        except Exception:
            continue
    base_str = f"({', '.join(bases)})" if bases else ""
    return f"class {node.name}{base_str}"


def _detect_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    """Detect FastAPI/Flask-style `@app.get("/path")` / `@router.post(...)`
    decorators."""
    for dec in node.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        func = call.func if call else dec
        if isinstance(func, ast.Attribute) and func.attr.lower() in _ROUTE_METHODS:
            method = func.attr.upper()
            path = None
            if call and call.args:
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    path = first.value
            return (path or "<dynamic>", method)
    return None
