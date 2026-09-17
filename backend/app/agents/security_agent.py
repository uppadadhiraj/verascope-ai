"""Security Agent (section 24).

Deliberately rule-based rather than LLM-based: pattern matches against real
file content are deterministic, reproducible, and cannot hallucinate a
vulnerability that isn't there. Every Finding stores the actual matched
text as `evidence` (section 24: "supported by repository evidence rather
than unsupported claims"). This also means security scanning works even
with no LLM provider configured at all -- it has no such dependency.

This is a real but intentionally-scoped MVP scanner: regex pattern matching
over source text, not full taint/dataflow analysis. False positives are
possible (flagged as such in remediation text where relevant); it is not
exhaustive. That tradeoff is explicit, not hidden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.enums import FindingSeverity
from app.models.file import RepositoryFile
from app.models.finding import Finding
from app.models.repository import Repository


@dataclass
class SecurityRule:
    finding_type: str
    severity: FindingSeverity
    pattern: re.Pattern
    explanation: str
    impact: str
    remediation: str
    languages: set[str] | None = None  # None = applies to all languages


_RULES: list[SecurityRule] = [
    SecurityRule(
        finding_type="hardcoded_secret",
        severity=FindingSeverity.CRITICAL,
        pattern=re.compile(
            r'\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|password|passwd|private[_-]?key)\s*[:=]\s*'
            r'[\'"][A-Za-z0-9_\-/+=]{8,}[\'"]',
            re.IGNORECASE,
        ),
        explanation="A credential-like value is hardcoded directly in source code.",
        impact="Anyone with read access to the repository (or its git history) can obtain this credential.",
        remediation="Move the value to an environment variable or secrets manager and load it at runtime; rotate the exposed credential.",
    ),
    SecurityRule(
        finding_type="aws_access_key",
        severity=FindingSeverity.CRITICAL,
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        explanation="A string matching the AWS Access Key ID format was found in source code.",
        impact="If valid, this key grants direct access to AWS resources under the associated account.",
        remediation="Revoke this key immediately in the AWS IAM console and use environment-based credentials instead.",
    ),
    SecurityRule(
        finding_type="private_key_material",
        severity=FindingSeverity.CRITICAL,
        pattern=re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        explanation="A private key block is committed directly in source code.",
        impact="Anyone with repository access can extract and use this private key.",
        remediation="Remove the key from source control, rotate it, and load keys from a secrets manager or mounted secret file instead.",
    ),
    SecurityRule(
        finding_type="sql_injection",
        severity=FindingSeverity.HIGH,
        pattern=re.compile(
            r'(?:execute|executemany|raw|cursor\.execute)\s*\(\s*(?:f[\'"]|[\'"][^\'")]*[\'"]\s*%|'
            r'[\'"][^\'")]*[\'"]\s*\+)',
            re.IGNORECASE,
        ),
        explanation="A SQL query appears to be built via string formatting/concatenation rather than parameterization.",
        impact="If any interpolated value originates from user input, this is a SQL injection vulnerability.",
        remediation="Use parameterized queries / prepared statements (e.g. cursor.execute(query, params)) instead of building SQL via string interpolation.",
        languages={"python"},
    ),
    SecurityRule(
        finding_type="command_injection",
        severity=FindingSeverity.HIGH,
        pattern=re.compile(
            r"(?:os\.system|subprocess\.(?:call|run|Popen|check_output))\s*\([^)]*(?:\+|%|f['\"]|\.format\()",
            re.IGNORECASE,
        ),
        explanation="A shell/process command appears to be constructed via string interpolation instead of a fixed argument list.",
        impact="If any interpolated value originates from user input, this can allow arbitrary command execution.",
        remediation="Pass command arguments as a list (subprocess.run([...], shell=False)) and never interpolate untrusted input into a shell string.",
        languages={"python"},
    ),
    SecurityRule(
        finding_type="command_injection",
        severity=FindingSeverity.HIGH,
        pattern=re.compile(r"child_process\.(?:exec|execSync)\s*\([^)]*(?:\+|\$\{)"),
        explanation="A shell command is being built via string concatenation/template literals before execution.",
        impact="If any interpolated value originates from user input, this can allow arbitrary command execution.",
        remediation="Use execFile/spawn with an argument array instead of exec with a concatenated string.",
        languages={"javascript", "typescript"},
    ),
    SecurityRule(
        finding_type="unsafe_eval",
        severity=FindingSeverity.HIGH,
        # Negative lookbehind for a preceding '.' so this doesn't fire on
        # unrelated methods that happen to be named exec (e.g. SQLModel /
        # SQLAlchemy's `session.exec(...)`) -- only bare eval()/exec() calls.
        pattern=re.compile(r"(?<!\.)\b(?:eval|exec)\s*\("),
        explanation="Use of eval()/exec() on what may be dynamic or externally-influenced input.",
        impact="Can allow arbitrary code execution if the evaluated string is influenced by untrusted input.",
        remediation="Avoid eval/exec entirely; use safe parsing (json.loads, ast.literal_eval) for the intended purpose.",
        languages={"python", "javascript", "typescript"},
    ),
    SecurityRule(
        finding_type="weak_crypto",
        severity=FindingSeverity.MEDIUM,
        pattern=re.compile(r"\bhashlib\.(?:md5|sha1)\s*\(|\bMessageDigest\.getInstance\([\'\"](?:MD5|SHA-?1)[\'\"]"),
        explanation="MD5 or SHA-1 is used, which are not suitable for password hashing or security-sensitive integrity checks.",
        impact="Weak hashing makes password cracking or integrity forgery significantly easier.",
        remediation="Use bcrypt/scrypt/argon2 for passwords, and SHA-256 or better for integrity checks.",
    ),
    SecurityRule(
        finding_type="insecure_cors",
        severity=FindingSeverity.MEDIUM,
        pattern=re.compile(r'allow_origins\s*=\s*\[\s*[\'"]\*[\'"]\s*\]|Access-Control-Allow-Origin[\'"]?\s*[:=]\s*[\'"]\*[\'"]'),
        explanation="CORS is configured to allow all origins ('*').",
        impact="Any website can make authenticated cross-origin requests to this API if credentials are also allowed.",
        remediation="Restrict allow_origins to a specific, known list of trusted origins.",
    ),
    SecurityRule(
        finding_type="debug_enabled",
        severity=FindingSeverity.MEDIUM,
        pattern=re.compile(r"\bDEBUG\s*=\s*True\b"),
        explanation="Debug mode appears to be hardcoded to enabled.",
        impact="Debug mode commonly exposes stack traces, source code, and internal configuration to end users.",
        remediation="Drive DEBUG from an environment variable and ensure it defaults to False in production.",
        languages={"python"},
    ),
    SecurityRule(
        finding_type="path_traversal_risk",
        severity=FindingSeverity.MEDIUM,
        pattern=re.compile(r"open\(\s*(?:os\.path\.join\([^)]*request|[^)]*request\.[\w.]*\[)"),
        explanation="A file is opened using a path that appears to be built from request-controlled input.",
        impact="Without validation, this can allow reading/writing files outside the intended directory.",
        remediation="Validate and normalize the path, and reject any path that resolves outside the intended base directory.",
        languages={"python"},
    ),
    SecurityRule(
        finding_type="insecure_deserialization",
        severity=FindingSeverity.HIGH,
        pattern=re.compile(r"\bpickle\.loads?\(|\byaml\.load\((?!.*Loader=yaml\.SafeLoader)"),
        explanation="Deserialization via pickle or an unsafe yaml.load() can execute arbitrary code for crafted input.",
        impact="If the deserialized data can be influenced by an untrusted source, this can lead to remote code execution.",
        remediation="Use json for untrusted data, or yaml.safe_load(); never unpickle untrusted input.",
        languages={"python"},
    ),
]

_MAX_FILE_BYTES_TO_SCAN = 500_000


def scan_repository(db: Session, repository: Repository, repo_dir_resolver) -> list[Finding]:
    """`repo_dir_resolver(repository_id) -> Path` avoids this module knowing
    about storage layout directly."""
    findings: list[Finding] = []
    repo_dir = repo_dir_resolver(str(repository.id))

    files = (
        db.query(RepositoryFile)
        .filter(RepositoryFile.repository_id == repository.id, RepositoryFile.is_binary.is_(False))
        .all()
    )

    for file_row in files:
        if file_row.size_bytes > _MAX_FILE_BYTES_TO_SCAN:
            continue
        abs_path = repo_dir / file_row.path
        if not abs_path.exists():
            continue
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for rule in _RULES:
            if rule.languages and file_row.language not in rule.languages:
                continue
            for match in rule.pattern.finditer(content):
                line_number = content.count("\n", 0, match.start()) + 1
                evidence_line = content.splitlines()[line_number - 1].strip() if line_number - 1 < len(content.splitlines()) else match.group(0)
                finding = Finding(
                    repository_id=repository.id,
                    finding_type=rule.finding_type,
                    severity=rule.severity,
                    file_path=file_row.path,
                    start_line=line_number,
                    end_line=line_number,
                    evidence=evidence_line[:500],
                    explanation=rule.explanation,
                    impact=rule.impact,
                    remediation=rule.remediation,
                )
                db.add(finding)
                findings.append(finding)

    db.commit()
    return findings
