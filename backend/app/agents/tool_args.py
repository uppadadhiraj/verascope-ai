"""Shared, lenient argument extraction for tool handlers.

Every tool schema in this codebase names the file-path argument `path`, but
models -- local/Ollama ones especially, observed directly with
llama3.1:8b -- frequently call it `file_path` instead. That's a plausible
enough alias that it's cheaper and more reliable to just accept it than to
rely on the model noticing a KeyError and retrying with the exact schema
name.
"""
from __future__ import annotations


def path_arg(args: dict) -> str:
    if "path" in args:
        return args["path"]
    if "file_path" in args:
        return args["file_path"]
    raise KeyError("path")
