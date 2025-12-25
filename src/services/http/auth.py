"""
HTTP API 认证模块
"""

from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import config

security = HTTPBearer(auto_error=False)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """
    验证 Bearer Token
    如果 HTTP_API_TOKEN 为空，则不启用认证
    """
    if not config.HTTP_API_TOKEN:
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="未提供认证信息",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if credentials.credentials != config.HTTP_API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="无效的 Token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return True
