"""
API Key 검증 모듈
Lambda에서 오는 요청의 X-API-Key 헤더를 검증
"""

from fastapi import Header, HTTPException, status
from typing import Annotated
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

if not INTERNAL_API_KEY:
    raise RuntimeError("INTERNAL_API_KEY 환경변수가 설정되지 않았습니다!")


async def verify_api_key(
    x_api_key: Annotated[str, Header(description="Internal API Key for Lambda communication")]
) -> bool:
    """
    X-API-Key 헤더 검증
    
    Args:
        x_api_key: 요청 헤더의 X-API-Key 값
    
    Returns:
        bool: 검증 성공 시 True
    
    Raises:
        HTTPException: API Key가 유효하지 않을 경우
    """
    if x_api_key != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )
    return True
