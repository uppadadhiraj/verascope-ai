from app.agents.security_agent import _RULES


def _matches(finding_type: str, text: str) -> bool:
    rules = [r for r in _RULES if r.finding_type == finding_type]
    return any(rule.pattern.search(text) for rule in rules)


def test_hardcoded_secret_detected():
    assert _matches("hardcoded_secret", 'API_KEY = "sk-abcdef1234567890"')


def test_unsafe_eval_detects_bare_eval_and_exec():
    assert _matches("unsafe_eval", "result = eval(user_input)")
    assert _matches("unsafe_eval", "exec(code_string)")


def test_unsafe_eval_does_not_false_positive_on_orm_exec_method():
    """Regression test: SQLModel/SQLAlchemy's `session.exec(...)` is not the
    eval()/exec() builtin and must not be flagged. This was a real false
    positive found while smoke-testing against tiangolo/full-stack-fastapi-template."""
    assert not _matches("unsafe_eval", "items = session.exec(statement).all()")
    assert not _matches("unsafe_eval", "count = session.exec(count_statement).one()")


def test_debug_enabled_detected():
    assert _matches("debug_enabled", "DEBUG = True")
    assert not _matches("debug_enabled", "DEBUG = False")


def test_insecure_cors_detected():
    assert _matches("insecure_cors", 'allow_origins=["*"]')


def test_weak_crypto_detected():
    assert _matches("weak_crypto", "hashlib.md5(password.encode())")
    assert not _matches("weak_crypto", "hashlib.sha256(data)")
