"""登录白名单 API 模型。"""

from pydantic import BaseModel


class LoginWhitelistUserCreate(BaseModel):
    name: str


class LoginWhitelistUserOut(BaseModel):
    id: int
    name: str


class LoginWhitelistDepartmentCreate(BaseModel):
    department_id: int


class LoginWhitelistDepartmentOut(BaseModel):
    id: int
    department_id: int
    name: str
    path: str


class LoginWhitelistDepartmentSearchOut(BaseModel):
    department_id: int
    name: str
    path: str


class LoginWhitelistOut(BaseModel):
    users: list[LoginWhitelistUserOut]
    departments: list[LoginWhitelistDepartmentOut]
