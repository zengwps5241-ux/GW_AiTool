from unittest.mock import patch, MagicMock
import json

import pytest


@pytest.mark.asyncio
async def test_get_access_token_success():
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "errcode": 0, "access_token": "test_token", "expires_in": 7200
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        from app.modules.auth.wechat_work import get_access_token
        token = await get_access_token("corp123", "secret456")
        assert token == "test_token"


@pytest.mark.asyncio
async def test_get_access_token_error():
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "errcode": 40001, "errmsg": "invalid credential"
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        from app.modules.auth.wechat_work import get_access_token
        with pytest.raises(RuntimeError, match="invalid credential"):
            await get_access_token("corp123", "bad_secret")


@pytest.mark.asyncio
async def test_get_user_id_by_code_success():
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "errcode": 0, "UserId": "ZhangSan"
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        from app.modules.auth.wechat_work import get_user_id_by_code
        user_id = await get_user_id_by_code("test_code", "token")
        assert user_id == "ZhangSan"


@pytest.mark.asyncio
async def test_get_user_detail_success():
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "errcode": 0,
        "userid": "ZhangSan",
        "name": "张三",
        "department": [1, 2],
        "position": "工程师",
        "mobile": "13800138000",
        "email": "zhangsan@example.com",
        "avatar": "https://example.com/avatar.jpg",
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        from app.modules.auth.wechat_work import get_user_detail
        detail = await get_user_detail("ZhangSan", "token")
        assert detail["name"] == "张三"
        assert detail["mobile"] == "13800138000"


@pytest.mark.asyncio
async def test_get_department_list_success():
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "errcode": 0,
        "department": [
            {"id": 1, "name": "研发部"},
            {"id": 2, "name": "后端组"},
        ]
    }).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        from app.modules.auth.wechat_work import get_department_list
        depts = await get_department_list("token")
        assert len(depts) == 2
        assert depts[0]["name"] == "研发部"
