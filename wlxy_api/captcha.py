"""成都职业培训网络学院登录无需图形验证码。"""

from __future__ import annotations


class NoCaptchaRequired:
    """站点账号密码登录不经过验证码流程。"""

    def solve(self) -> None:
        return None
