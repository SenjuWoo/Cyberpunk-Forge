"""RED .tweak source (the TweakDB format CDPR ships in tools/redmod/tweaks and TweakXL loads from r6/tweaks).

A structural parser: records, statements, values, brackets, strings. It does not
know field types; TweakXL reports type errors in its own log at game start.
Calibrated against every vanilla .tweak file of a 2.5 install (0 findings).
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import read_text

_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r\f\v]+)
  | (?P<nl>\n)
  | (?P<lcomment>//[^\n]*)
  | (?P<bcomment>/\*.*?\*/)
  | (?P<str>"[^"\n]*")
  | (?P<badstr>"[^"\n]*)
  | (?P<op>\+=|-=|=)
  | (?P<punct>[{}\[\]();,:<>])
  | (?P<word>-?[\w.#$@]+)
""", re.X | re.S)

_RECORD_NAME = re.compile(r"^[A-Za-z_][\w]*(?:\.[\w]+)*$")
_DOTTED = re.compile(r"^[A-Za-z_][\w]*(?:\.[\w]+)+$")


class TweakSyntaxError(Exception):
    def __init__(self, line: int, code: str, message: str):
        super().__init__(message)
        self.line, self.code, self.message = line, code, message


def tokenize(text: str) -> tuple[list[tuple[str, str, int]], str, list[str]]:
    """Return (tokens, package, using). package/using lines are directives without ';'."""
    package, using = "", []
    kept = []
    for raw in text.splitlines():
        code = raw.split("//", 1)[0].strip()
        m = re.match(r"^package\s+([\w.]+)\s*;?\s*$", code)
        u = re.match(r"^using\s+([\w.,\s]+?)\s*;?\s*$", code)
        if m and not package:
            package = m.group(1)
            kept.append("")
        elif u:
            using += [x.strip() for x in u.group(1).split(",") if x.strip()]
            kept.append("")
        else:
            kept.append(raw)
    src = "\n".join(kept)
    tokens, line, pos = [], 1, 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise TweakSyntaxError(line, "TWEAK-SRC-CHAR", f"unexpected character {src[pos]!r}")
        kind = m.lastgroup
        val = m.group()
        if kind == "badstr":
            raise TweakSyntaxError(line, "TWEAK-SRC-STRING", "string is not closed on this line")
        if kind in ("str", "op", "punct", "word"):
            tokens.append((kind, val, line))
        line += val.count("\n")
        pos = m.end()
    return tokens, package, using


class _Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0
        self.records: dict[str, dict] = {}
        self.flats: dict[str, int] = {}
        self.strings: list[tuple[str, int]] = []

    def peek(self, k: int = 0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("eof", "", self.t[-1][2] if self.t else 1)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, val: str, code: str, what: str):
        tok = self.take()
        if tok[1] != val:
            raise TweakSyntaxError(tok[2], code, f"expected '{val}' {what}, found {self._show(tok)}")
        return tok

    @staticmethod
    def _show(tok):
        return "end of file" if tok[0] == "eof" else repr(tok[1])

    def file(self):
        while self.peek()[0] != "eof":
            tok = self.peek()
            if tok[1] == ";":
                self.take()
                continue
            if tok[1] == "[":
                self.attributes()
                continue
            if tok[0] != "word":
                raise TweakSyntaxError(tok[2], "TWEAK-SRC-TOP", f"expected a record or a flat, found {self._show(tok)}")
            if self.peek(1)[1] in (":", "{"):
                self.record()
            else:
                # Top-level flat: float baseSpeed = 10.f;  string[] list = [...];
                name = self.statement()
                self.flats.setdefault(name, tok[2])

    def attributes(self):
        """[ notQueryable ] before a record."""
        self.take()
        while self.peek()[1] != "]":
            t = self.take()
            if t[0] == "eof" or t[1] in ("{", "}", ";", "["):
                raise TweakSyntaxError(t[2], "TWEAK-SRC-ATTRIBUTE", f"record attribute list is not closed (found {self._show(t)})")
        self.take()

    def record(self):
        tok = self.take()
        if not _RECORD_NAME.match(tok[1]):
            raise TweakSyntaxError(tok[2], "TWEAK-SRC-TOP", f"'{tok[1]}' is not a valid record name")
        base = None
        if self.peek()[1] == ":":
            self.take()
            b = self.take()
            if b[0] != "word":
                raise TweakSyntaxError(b[2], "TWEAK-SRC-BASE-SYNTAX", f"expected a base record after ':', found {self._show(b)}")
            base = b[1]
        if tok[1] in self.records:
            raise TweakSyntaxError(tok[2], "TWEAK-SRC-DUP", f"record '{tok[1]}' is defined twice in this file")
        self.records[tok[1]] = {"base": base, "line": tok[2]}
        self.expect("{", "TWEAK-SRC-BRACE", f"to open record '{tok[1]}'")
        self.body("}")

    def body(self, close: str):
        """Statements until `close`."""
        while True:
            tok = self.peek()
            if tok[1] == close:
                self.take()
                return
            if tok[0] == "eof":
                raise TweakSyntaxError(tok[2], "TWEAK-SRC-UNCLOSED", f"'{ {'}': '{', ']': '['}[close] }' is never closed")
            if tok[1] == ";":
                self.take()
                continue
            self.statement()

    def statement(self) -> str:
        """[type] name (= | += | -=) value ;  Returns the field name."""
        start = self.peek()
        depth = 0
        name = start[1]
        # Left side: an optional type (fk< X >[], CName, Float[]...) and the field name.
        while True:
            t = self.peek()
            if t[0] == "op" and depth == 0:
                break
            if t[0] in ("eof", "str") or t[1] in ("{", "}", ";", ","):
                raise TweakSyntaxError(t[2], "TWEAK-SRC-STATEMENT",
                                       f"statement starting with {self._show(start)} has no '=' (found {self._show(t)})")
            if t[1] in ("<", "["):
                depth += 1
            elif t[1] in (">", "]"):
                depth -= 1
            elif t[0] == "word" and depth == 0:
                name = t[1]
            self.take()
        self.take()  # the operator
        self.value()
        end = self.peek()
        if end[1] != ";":
            prev = self.t[self.i - 1]
            raise TweakSyntaxError(prev[2], "TWEAK-SRC-SEMICOLON",
                                   f"missing ';' after the value of '{name}' (next is {self._show(end)})")
        self.take()
        return name

    def value(self):
        tok = self.take()
        if tok[0] == "str":
            self.strings.append((tok[1][1:-1], tok[2]))
            return
        if tok[0] == "word":
            return
        if tok[1] == "[":
            self.items("]")
            return
        if tok[1] == "(":
            self.items(")")
            return
        if tok[1] == "{":
            self.body("}")
            # An inline record may name its base after the closing brace: { ... } : AIActionAND
            if self.peek()[1] == ":":
                self.take()
                b = self.take()
                if b[0] != "word":
                    raise TweakSyntaxError(b[2], "TWEAK-SRC-BASE-SYNTAX", f"expected a base record after ':', found {self._show(b)}")
            return
        raise TweakSyntaxError(tok[2], "TWEAK-SRC-VALUE", f"expected a value, found {self._show(tok)}")

    def items(self, close: str):
        """Comma-separated values; a trailing comma is allowed. Inline records may carry a name/base header."""
        while True:
            tok = self.peek()
            if tok[1] == close:
                self.take()
                return
            if tok[0] == "eof":
                raise TweakSyntaxError(tok[2], "TWEAK-SRC-UNCLOSED", f"'{ {']': '[', ')': '('}[close] }' is never closed")
            if tok[0] == "word" and (self.peek(1)[1] == "{" or (self.peek(1)[1] == ":" and self.peek(3)[1] == "{")):
                self.take()
                if self.peek()[1] == ":":
                    self.take()
                    self.take()
            self.value()
            nxt = self.peek()
            if nxt[1] == ",":
                self.take()
            elif nxt[1] != close:
                prev = self.t[self.i - 1]
                raise TweakSyntaxError(prev[2], "TWEAK-SRC-COMMA", f"missing ',' between list items (next is {self._show(nxt)})")


def parse(text: str) -> dict:
    """{"package", "using", "records": {Name: {base, line}}, "flats": {name: line}, "strings": [(s, line)], "error"}"""
    try:
        tokens, package, using = tokenize(text)
    except TweakSyntaxError as e:
        return {"package": "", "using": [], "records": {}, "flats": {}, "strings": [],
                "error": {"line": e.line, "code": e.code, "message": e.message}}
    p = _Parser(tokens)
    err = None
    try:
        p.file()
    except TweakSyntaxError as e:
        err = {"line": e.line, "code": e.code, "message": e.message}
    return {"package": package, "using": using, "records": p.records, "flats": p.flats, "strings": p.strings,
            "error": err}


def parse_file(path: Path) -> dict:
    return parse(read_text(path))


def full_names(parsed: dict) -> dict[str, dict]:
    pkg = parsed["package"]
    # A dotted record name is already fully qualified (mods often skip `package`).
    return {(f"{pkg}.{n}" if pkg and "." not in n else n): r for n, r in parsed["records"].items()}


def base_candidates(parsed: dict, base: str) -> list[str]:
    """A base may be a full name, a name in this package, or a name in a `using` package."""
    out = [base]
    if parsed["package"]:
        out.append(f"{parsed['package']}.{base}")
    out += [f"{u}.{base}" for u in parsed["using"]]
    return out


def looks_like_record(s: str) -> bool:
    return bool(_DOTTED.match(s)) and s[:1].isupper() and not s.startswith("LocKey")
