"""Parse username + password from a single combined credential string.

Supports Chinese/English labels, varied punctuation, brackets, 是/为 connectors,
and label-on-next-line layouts common in pasted chat / Excel cells.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# 账号侧标签（长词在前，避免短词误匹配）
_USER_TERMS = (
    "登录账号", "登陆账号", "登录名", "登陆名", "用户名称", "用户名",
    "手机号码", "手机号", "电子邮件", "账户名", "账号名", "会员号",
    "账号", "帐号", "账户", "帐户", "用户", "工号", "学号", "手机", "电话", "邮箱",
    "account", "username", "login", "email", "mail", "user",
)
_PASS_TERMS = (
    "登录密码", "登陆密码", "用户密码", "账户密码", "帐户密码", "帐号密码",
    "密码", "口令", "通行码",
    "password", "pwd", "pass",
)

_USER_LABEL = "(?:" + "|".join(re.escape(t) for t in _USER_TERMS) + ")"
_PASS_LABEL = "(?:" + "|".join(re.escape(t) for t in _PASS_TERMS) + ")"
_VALUE_SEP = r"[:：=是为\-—–|>|→]"
_BRACKET_OPEN = r"[\[【「《(（]"
_BRACKET_CLOSE = r"[\]】」》)）]"


class ParsedCredentials(NamedTuple):
    username: str
    password: str


class CredentialParseError(ValueError):
    """Raised when combined credential text cannot be split into user + password."""


def _clean_value(val: str) -> str:
    v = (val or "").strip().strip("\"'""''")
    v = re.sub(rf"^{_BRACKET_OPEN}+|{_BRACKET_CLOSE}+$", "", v)
    return v.strip().strip("，,;；.")


def _normalize_spaces(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[，,;；&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _inline_from_raw(raw: str) -> str:
    return _normalize_spaces(raw.replace("\r\n", " ").replace("\n", " "))


def _has_explicit_label(inline: str) -> bool:
    return bool(
        re.search(rf"(?i)(?:^|[\s]){_USER_LABEL}\s*(?:{_VALUE_SEP}|[\s{_BRACKET_OPEN}])", inline)
        or re.search(rf"(?i)(?:^|[\s]){_PASS_LABEL}\s*(?:{_VALUE_SEP}|[\s{_BRACKET_OPEN}])", inline)
    )


def _try_labeled_pair(inline: str) -> ParsedCredentials | None:
    """一行内：账号…密码…（多种分隔符与括号）。"""
    patterns = [
        # 【账号】u【密码】p
        rf"(?i){_BRACKET_OPEN}{_USER_LABEL}{_BRACKET_CLOSE}\s*(.+?)\s*"
        rf"{_BRACKET_OPEN}{_PASS_LABEL}{_BRACKET_CLOSE}\s*(.+)$",
        # 账号【u】密码【p】
        rf"(?i){_USER_LABEL}{_BRACKET_OPEN}(.+?){_BRACKET_CLOSE}\s*"
        rf"{_PASS_LABEL}{_BRACKET_OPEN}(.+?){_BRACKET_CLOSE}\s*$",
        # 账号是xxx密码是yyy（无空格紧凑）
        rf"(?i){_USER_LABEL}\s*{_VALUE_SEP}\s*(.+?){_PASS_LABEL}\s*{_VALUE_SEP}\s*(.+)$",
        # 账号【u】密码【p】 / 【账号】u 【密码】p
        rf"(?i){_BRACKET_OPEN}?{_USER_LABEL}{_BRACKET_CLOSE}?\s*{_VALUE_SEP}?\s*"
        rf"(.+?)\s+{_BRACKET_OPEN}?{_PASS_LABEL}{_BRACKET_CLOSE}?\s*{_VALUE_SEP}?\s*(.+)$",
        # 账号 xxx 密码 yyy（空格分隔标签）
        rf"(?i){_USER_LABEL}\s+(.+?)\s+{_PASS_LABEL}\s+(.+)$",
        # 账号:xxx 密码:yyy（带空格）
        rf"(?i){_USER_LABEL}\s*{_VALUE_SEP}\s*(.+?)\s+{_PASS_LABEL}\s*{_VALUE_SEP}\s*(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, inline)
        if not m:
            continue
        user, pwd = _clean_value(m.group(1)), _clean_value(m.group(2))
        if user and pwd:
            return ParsedCredentials(user, pwd)
    return None


def _try_multiline_labeled(raw: str) -> ParsedCredentials | None:
    """多行：账号：xxx / 标签独占一行、值在下一行。"""
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", raw) if ln.strip()]
    user_val = pass_val = None
    i = 0
    while i < len(lines):
        ln = lines[i]

        def take_after_label(label_pat: str) -> str | None:
            nonlocal i
            # 整行仅标签
            if re.fullmatch(rf"(?i){label_pat}\s*{_VALUE_SEP}?\s*", ln):
                if i + 1 < len(lines):
                    i += 1
                    return _clean_value(lines[i])
                return None
            # 标签【值】或 标签：值
            m = re.match(
                rf"(?i)^(?:{_BRACKET_OPEN})?{label_pat}(?:{_BRACKET_CLOSE})?"
                rf"\s*{_VALUE_SEP}?\s*(.+)$",
                ln,
            )
            if m:
                return _clean_value(m.group(1))
            # 【标签】值
            m = re.match(
                rf"(?i)^{_BRACKET_OPEN}{label_pat}{_BRACKET_CLOSE}\s*{_VALUE_SEP}?\s*(.+)$",
                ln,
            )
            if m:
                return _clean_value(m.group(1))
            return None

        u = take_after_label(_USER_LABEL)
        if u is not None:
            user_val = u
            i += 1
            continue
        p = take_after_label(_PASS_LABEL)
        if p is not None:
            pass_val = p
            i += 1
            continue
        i += 1

    if user_val and pass_val:
        return ParsedCredentials(user_val, pass_val)
    return None


def _try_kv_pairs(inline: str) -> ParsedCredentials | None:
    """账号=xx&密码=yy 或 账号=xx 密码=yy（normalize 后空格分隔）。"""
    user_val = pass_val = None
    for part in inline.split():
        m = re.match(rf"(?i)^{_USER_LABEL}\s*=\s*(.+)$", part)
        if m:
            user_val = _clean_value(m.group(1))
            continue
        m = re.match(rf"(?i)^{_PASS_LABEL}\s*=\s*(.+)$", part)
        if m:
            pass_val = _clean_value(m.group(1))
    if user_val and pass_val:
        return ParsedCredentials(user_val, pass_val)
    return None


def _try_pipe_four(inline: str) -> ParsedCredentials | None:
    """账号|user|密码|pass"""
    parts = [p.strip() for p in inline.split("|")]
    if len(parts) == 4 and re.fullmatch(rf"(?i){_USER_LABEL}", parts[0]) and re.fullmatch(rf"(?i){_PASS_LABEL}", parts[2]):
        u, p = _clean_value(parts[1]), _clean_value(parts[3])
        if u and p:
            return ParsedCredentials(u, p)
    return None


def parse_combined_credentials(text: str) -> ParsedCredentials:
    """Return (username, password) parsed from one combined string."""
    if not text or not str(text).strip():
        raise CredentialParseError("请输入账号密码")

    raw = str(text).strip()
    inline = _inline_from_raw(raw)

    for fn in (
        lambda: _try_pipe_four(inline),
        lambda: _try_labeled_pair(inline),
        lambda: _try_multiline_labeled(raw),
        lambda: _try_kv_pairs(inline),
    ):
        result = fn()
        if result:
            return result

    if not _has_explicit_label(inline):
        for sep in ("：", ":"):
            if sep in inline:
                left, right = inline.split(sep, 1)
                left, right = _clean_value(left), _clean_value(right)
                if left and right:
                    return ParsedCredentials(left, right)

        if "/" in inline and inline.count("/") == 1:
            left, right = inline.split("/", 1)
            left, right = _clean_value(left), _clean_value(right)
            if left and right and " " not in left and " " not in right:
                return ParsedCredentials(left, right)

    parts = inline.split()
    if len(parts) >= 2:
        return ParsedCredentials(parts[0], " ".join(parts[1:]))

    raise CredentialParseError(
        "无法识别账号和密码。支持：账号/密码标签（含帐号、登录名、手机号等）、"
        "冒号/等号/「是」「为」连接、括号包裹、多行标注、或空格分隔的两段文本"
    )


if __name__ == "__main__":
    _cases = [
        ("testuser secret123", "testuser", "secret123"),
        ("testuser:secret123", "testuser", "secret123"),
        ("账号 testuser 密码 secret123", "testuser", "secret123"),
        ("账号：testuser 密码：secret123", "testuser", "secret123"),
        ("账号:testuser\n密码:secret123", "testuser", "secret123"),
        ("账号是zhangsan密码是mima123", "zhangsan", "mima123"),
        ("账号为 zhangsan 密码为 mima123", "zhangsan", "mima123"),
        ("【账号】zhangsan【密码】mima123", "zhangsan", "mima123"),
        ("账号【zhangsan】密码【mima123】", "zhangsan", "mima123"),
        ("登录账号=foo@x.com 登录密码=barbaz", "foo@x.com", "barbaz"),
        ("账号|zhangsan|密码|mima123", "zhangsan", "mima123"),
        ("手机号 13800138000 口令 abc123", "13800138000", "abc123"),
        ("账号\nzhangsan\n密码\nmima123", "zhangsan", "mima123"),
        ("用户名/密码: zhang/mima", None, None),  # skip — ambiguous
        ("username: foo password: bar", "foo", "bar"),
        ("user/pass", "user", "pass"),
        ("帐号：test  帐户密码：pwd", "test", "pwd"),
        ("工号 E001 密码 pass99", "E001", "pass99"),
    ]
    ok = fail = 0
    for s, eu, ep in _cases:
        if eu is None:
            continue
        try:
            u, p = parse_combined_credentials(s)
            assert u == eu and p == ep, (u, p)
            print(f"OK  {s!r} -> {u!r}, {p!r}")
            ok += 1
        except Exception as exc:
            print(f"FAIL {s!r}: {exc}")
            fail += 1
    print(f"\n{ok} passed, {fail} failed")
