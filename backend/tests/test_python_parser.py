from app.services.ingestion.parser.python_parser import parse_python

SAMPLE = '''
import os
from app.core.config import get_settings
from ..models import User

class AuthService:
    """Handles authentication."""

    def __init__(self, db):
        self.db = db

    def login(self, email: str, password: str) -> bool:
        return True


def standalone_function(x: int) -> int:
    return x + 1


@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}
'''


def test_parse_python_extracts_imports():
    result = parse_python(SAMPLE)
    raws = {i.raw for i in result.imports}
    assert "os" in raws
    assert "app.core.config" in raws
    assert "..models" in raws


def test_parse_python_extracts_class_and_methods():
    result = parse_python(SAMPLE)
    classes = [s for s in result.symbols if s.symbol_type == "class"]
    methods = [s for s in result.symbols if s.symbol_type == "method"]

    assert any(c.name == "AuthService" for c in classes)
    assert any(m.name == "login" and m.parent_name == "AuthService" for m in methods)


def test_parse_python_extracts_standalone_function():
    result = parse_python(SAMPLE)
    functions = [s for s in result.symbols if s.symbol_type == "function" and s.parent_name is None]
    assert any(f.name == "standalone_function" for f in functions)


def test_parse_python_detects_route():
    result = parse_python(SAMPLE)
    routes = [s for s in result.symbols if s.symbol_type == "route"]
    assert len(routes) == 1
    assert routes[0].route_path == "/users/{user_id}"
    assert routes[0].http_method == "GET"


def test_parse_python_syntax_error_does_not_raise():
    result = parse_python("def broken(:\n    pass")
    assert result.error is not None
    assert result.symbols == []
