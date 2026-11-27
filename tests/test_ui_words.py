"""Every error the server can show a user has Italian words in the UI.

The server writes its errors in English; app/static/i18n.js says them in
Italian (SERVER_ERRORS_IT). This reads every message app/*.py can raise and
fails when one has no Italian pattern, or when a pattern no longer matches
any message (a message was reworded and its translation left behind).
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Messages only a developer or a misused API sees: they stay English.
INTERNAL = [
    r"^. must be an object$", r"^. is not an editable field$", r"^. must be text$",
    r"^size can only be thumb$", r"^action must be one of .$", r"^ids must be a list of track ids$",
    r"^scope must be 'history' or 'completed'$",
    r"^. is not one of .$", r"^cursor does not belong to this list$",
    r"^limit must be between 1 and (500|200)$", r"^selection must hold the track ids$",
    r"^steps must be a non-empty list$", r"^the edit must be an object$",
    r"^notices not found in this build$", r"^license not found in this build$",
    r'^send \{"url": "https://\.\.\."\} or upload an image$',
]


def _texts(node) -> list[str]:
    """The messages an expression can build, with "." for each value put in."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "."
                        for v in node.values)]
    if isinstance(node, ast.IfExp):
        return _texts(node.body) + _texts(node.orelse)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [a + b for a in (_texts(node.left) or ["."]) for b in (_texts(node.right) or ["."])]
    return []


def server_messages() -> set[str]:
    found = set()
    for path in (ROOT / "app").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("HTTPException", "LibraryError")
                    and len(node.args) >= 2):
                found.update(_texts(node.args[1]))
            if isinstance(node, ast.FunctionDef) and node.name == "patch_problem":
                for ret in ast.walk(node):
                    if isinstance(ret, ast.Return) and ret.value is not None:
                        found.update(_texts(ret.value))
    return found


def italian_patterns() -> list[re.Pattern]:
    js = (ROOT / "app" / "static" / "i18n.js").read_text(encoding="utf-8")
    block = js[js.index("const SERVER_ERRORS_IT = ["):js.index("];", js.index("const SERVER_ERRORS_IT"))]
    return [re.compile(p.replace(r"\/", "/")) for p in re.findall(r"\[/(.+?)/,", block)]


def test_every_message_a_user_can_see_has_italian_words():
    patterns, internal = italian_patterns(), [re.compile(p) for p in INTERNAL]
    missing = []
    for message in sorted(server_messages()):
        candidates = {message, message.replace(".", "1")}
        if not any(p.search(c) for p in patterns + internal for c in candidates):
            missing.append(message)
    assert not missing, f"add these to SERVER_ERRORS_IT in app/static/i18n.js (or to INTERNAL): {missing}"


def test_every_italian_pattern_still_matches_a_server_message():
    messages = server_messages()
    stale = [p.pattern for p in italian_patterns()
             if not any(p.search(m) or p.search(m.replace(".", "1")) for m in messages)]
    assert not stale, f"these patterns match no server message any more: {stale}"
