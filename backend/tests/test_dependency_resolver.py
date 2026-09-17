from app.services.ingestion.dependency_resolver import resolve_imports
from app.services.ingestion.parser.base import ExtractedImport


def test_resolve_python_absolute_import():
    imports_by_file = {"app/api/routes/auth.py": [ExtractedImport(raw="app.core.security")]}
    language_by_file = {"app/api/routes/auth.py": "python", "app/core/security.py": "python"}

    resolved = resolve_imports(imports_by_file, language_by_file)
    assert resolved[0].target_file == "app/core/security.py"


def test_resolve_python_relative_import_one_level_up():
    # `from ..security import x` in app/api/routes/auth.py: one leading dot
    # beyond the current package (app.api.routes) means the PARENT package,
    # app.api -- so this resolves to app/api/security.py, not app/security.py.
    imports_by_file = {"app/api/routes/auth.py": [ExtractedImport(raw="..security", imported_names=["hash_password"])]}
    language_by_file = {"app/api/routes/auth.py": "python", "app/api/security.py": "python"}

    resolved = resolve_imports(imports_by_file, language_by_file)
    assert resolved[0].target_file == "app/api/security.py"


def test_resolve_python_relative_import_two_levels_up():
    # `from ...core.security import x` in app/api/routes/auth.py: three dots
    # reaches the grandparent package, app -- so this resolves to
    # app/core/security.py.
    imports_by_file = {"app/api/routes/auth.py": [ExtractedImport(raw="...core.security", imported_names=["hash_password"])]}
    language_by_file = {"app/api/routes/auth.py": "python", "app/core/security.py": "python"}

    resolved = resolve_imports(imports_by_file, language_by_file)
    assert resolved[0].target_file == "app/core/security.py"


def test_resolve_unresolvable_import_keeps_raw_reference():
    imports_by_file = {"app/main.py": [ExtractedImport(raw="fastapi")]}
    language_by_file = {"app/main.py": "python"}

    resolved = resolve_imports(imports_by_file, language_by_file)
    assert resolved[0].target_file is None
    assert resolved[0].raw == "fastapi"


def test_resolve_js_relative_import():
    imports_by_file = {"src/pages/Login.tsx": [ExtractedImport(raw="../api/client")]}
    language_by_file = {"src/pages/Login.tsx": "typescript", "src/api/client.ts": "typescript"}

    resolved = resolve_imports(imports_by_file, language_by_file)
    assert resolved[0].target_file == "src/api/client.ts"
