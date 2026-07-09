# DEPRECATED: 企微认证，保留以备未来扩展
# 以下代码为原企业微信 API 调用封装，已切换为自建注册登录体系。
# 如需恢复企微认证，取消注释即可。

# """企业微信 API 调用封装。
#
# 使用 urllib 做 HTTP 请求,通过 asyncio 线程池包装为异步接口,
# 避免引入额外依赖。
# """
#
# import asyncio
# import json
# import urllib.parse
# import urllib.request
# from typing import Any
#
#
# async def _http_get(url: str) -> dict[str, Any]:
#     """异步 GET 请求,返回 JSON 解析结果。"""
#
#     def _sync_get() -> dict[str, Any]:
#         req = urllib.request.Request(url, method="GET")
#         with urllib.request.urlopen(req, timeout=30) as resp:
#             return json.loads(resp.read().decode("utf-8"))
#
#     return await asyncio.get_running_loop().run_in_executor(None, _sync_get)
#
#
# async def _http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
#     """异步 POST 请求,返回 JSON 解析结果。"""
#
#     def _sync_post() -> dict[str, Any]:
#         data = json.dumps(body, ensure_ascii=False).encode("utf-8")
#         req = urllib.request.Request(
#             url,
#             data=data,
#             method="POST",
#             headers={"Content-Type": "application/json"},
#         )
#         with urllib.request.urlopen(req, timeout=30) as resp:
#             return json.loads(resp.read().decode("utf-8"))
#
#     return await asyncio.get_running_loop().run_in_executor(None, _sync_post)
#
#
# async def get_access_token(corp_id: str, secret: str) -> str:
#     """获取企业微信应用 access_token。"""
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
#         f"?corpid={urllib.parse.quote(corp_id)}"
#         f"&corpsecret={urllib.parse.quote(secret)}"
#     )
#     data = await _http_get(url)
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微获取 access_token 失败: {data}")
#     return str(data["access_token"])
#
#
# async def get_user_id_by_code(code: str, access_token: str) -> str:
#     """用 OAuth code 换取用户 userid。"""
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo"
#         f"?access_token={urllib.parse.quote(access_token)}"
#         f"&code={urllib.parse.quote(code)}"
#     )
#     data = await _http_get(url)
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微 code 换 userid 失败: {data}")
#     if "UserId" not in data:
#         raise RuntimeError(f"企微返回 OpenId,该用户非企业成员: {data}")
#     return str(data["UserId"])
#
#
# async def get_user_detail(user_id: str, access_token: str) -> dict[str, Any]:
#     """用 userid 获取用户详情。"""
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/user/get"
#         f"?access_token={urllib.parse.quote(access_token)}"
#         f"&userid={urllib.parse.quote(user_id)}"
#     )
#     data = await _http_get(url)
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微获取用户详情失败: {data}")
#     return data
#
#
# async def get_department_list(access_token: str) -> list[dict[str, Any]]:
#     """获取全量部门列表,用于将部门 ID 映射为名称。"""
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/department/list"
#         f"?access_token={urllib.parse.quote(access_token)}"
#     )
#     data = await _http_get(url)
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微获取部门列表失败: {data}")
#     return list(data.get("department", []))
#
#
# async def auth_get_user_info(code: str, access_token: str) -> dict[str, Any]:
#     """用 OAuth code 换取用户身份和 user_ticket（用于获取敏感信息）。
#
#     对应接口: POST /cgi-bin/auth/getuserinfo
#     """
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
#         f"?access_token={urllib.parse.quote(access_token)}"
#         f"&code={urllib.parse.quote(code)}"
#     )
#     data = await _http_get(url)
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微 auth/getuserinfo 失败: {data}")
#     return data
#
#
# async def auth_get_user_detail(user_ticket: str, access_token: str) -> dict[str, Any]:
#     """用 user_ticket 获取用户敏感信息（手机、邮箱、头像等）。
#
#     对应接口: POST /cgi-bin/auth/getuserdetail
#     需要在 OAuth 授权时使用 scope=snsapi_privateinfo 才能获取 user_ticket。
#     """
#     url = (
#         "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserdetail"
#         f"?access_token={urllib.parse.quote(access_token)}"
#     )
#     data = await _http_post(url, {"user_ticket": user_ticket})
#     if data.get("errcode", 0) != 0:
#         raise RuntimeError(f"企微 auth/getuserdetail 失败: {data}")
#     return data
