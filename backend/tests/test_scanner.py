from pathlib import Path

from app.core.config import Settings
from app.services.ingestion.scanner import scan_repository


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_storage_dir=str(tmp_path),
        workspace_storage_dir=str(tmp_path),
        max_file_size_bytes=1_000_000,
        max_repo_files=1000,
    )


def test_scan_repository_ignores_configured_directories(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hi')")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports = {}")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")

    settings = _make_settings(tmp_path)
    result = scan_repository(tmp_path, settings)

    paths = {f.path for f in result.files}
    assert "app/main.py" in paths
    assert not any(p.startswith("node_modules/") for p in paths)
    assert not any(p.startswith(".git/") for p in paths)


def test_scan_repository_skips_oversized_files(tmp_path: Path):
    (tmp_path / "big.py").write_text("x = 1\n" * 10)
    settings = _make_settings(tmp_path)
    settings.max_file_size_bytes = 10  # force everything to look "too large"

    result = scan_repository(tmp_path, settings)
    big_file = next(f for f in result.files if f.path == "big.py")
    assert big_file.skipped_reason is not None
    assert "too large" in big_file.skipped_reason


def test_scan_repository_flags_binary_content(tmp_path: Path):
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02binary")
    settings = _make_settings(tmp_path)

    result = scan_repository(tmp_path, settings)
    binary_file = next(f for f in result.files if f.path == "data.bin")
    assert binary_file.is_binary
