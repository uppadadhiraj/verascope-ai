from app.services.ingestion.language_detect import (
    detect_language,
    is_config_file,
    is_documentation_file,
    is_test_file,
)


def test_detect_language_common_extensions():
    assert detect_language("app/main.py") == "python"
    assert detect_language("src/index.tsx") == "typescript"
    assert detect_language("src/App.jsx") == "javascript"
    assert detect_language("Main.java") == "java"
    assert detect_language("README.md") == "markdown"
    assert detect_language("unknown.xyz") is None


def test_is_test_file_by_directory_and_filename():
    assert is_test_file("tests/test_auth.py")
    assert is_test_file("app/test_utils.py")
    assert is_test_file("src/components/__tests__/Button.test.tsx")
    assert is_test_file("src/api/user.spec.ts")
    assert not is_test_file("app/services/auth.py")


def test_is_config_file():
    assert is_config_file("package.json")
    assert is_config_file("backend/requirements.txt")
    assert is_config_file("Dockerfile")
    assert not is_config_file("app/main.py")


def test_is_documentation_file():
    assert is_documentation_file("README.md")
    assert not is_documentation_file("app/main.py")
