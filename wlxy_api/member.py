from __future__ import annotations

from typing import Any

from .client import HttpClient
from .responses import parse_member_response, require_data


class MemberService:
    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def get_profile_by_token(self) -> dict[str, Any]:
        data = self.client.api_get_safe("/user/user/get_userByToken")
        profile = require_data(data)
        if isinstance(profile, dict):
            self.client.user_profile = profile
        return profile

    def query_user(self, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or (self.client.user_profile or {}).get("userId")
        if not uid:
            raise RuntimeError("缺少 userId，请先登录")
        data = self.client.api_get_safe("/user/user/query_user", {"userId": uid})
        return require_data(data)

    def query_userinfo_progress(self, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or (self.client.user_profile or {}).get("userId")
        if not uid:
            raise RuntimeError("缺少 userId，请先登录")
        data = self.client.api_get_safe("/user/edu/query_userinfo_progress", {"userId": uid})
        return require_data(data)

    def probe_session(self) -> bool:
        if not self.client.token:
            return False
        try:
            data = self.client.api_get_safe("/user/user/get_userByToken")
            return parse_member_response(data).ok
        except Exception:
            return False
