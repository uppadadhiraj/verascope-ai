from app.agents.fix_tools import _placeholder_content_error


def test_detects_rest_remains_the_same_placeholder():
    """Regression test: found live during testing -- llama3.1:8b replaced an
    entire file's content with a few lines plus this exact placeholder
    comment, producing an unparseable file. modify_file/create_file must
    reject this instead of silently writing garbage."""
    content = (
        'if token == "invalid":\n'
        "    raise InvalidTokenError()\n"
        "    # ... rest of the function remains the same ...\n"
    )
    assert _placeholder_content_error(content) is not None


def test_detects_ellipsis_comment_placeholder():
    content = "def f():\n    pass\n# ...\n"
    assert _placeholder_content_error(content) is not None


def test_detects_bracketed_rest_of_code_placeholder():
    content = "def f():\n    pass\n<rest of code>\n"
    assert _placeholder_content_error(content) is not None


def test_does_not_flag_legitimate_complete_code():
    content = (
        "def get_current_user(token):\n"
        "    try:\n"
        "        return validate_token(token)\n"
        "    except InvalidTokenError:\n"
        '        raise PermissionError("unauthorized")\n'
    )
    assert _placeholder_content_error(content) is None


def test_does_not_flag_code_containing_the_word_unchanged():
    """A real docstring/comment using the word 'unchanged' in a normal
    sentence should not be flagged -- only the specific elision idioms."""
    content = "def f():\n    # state is unchanged by this operation\n    return 1\n"
    assert _placeholder_content_error(content) is None
