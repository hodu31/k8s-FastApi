"""
FastAPI 메인 애플리케이션
Lambda와 Kubernetes를 연결하는 중간 API 서버
"""

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import os
from dotenv import load_dotenv

from auth import verify_api_key
from k8s_manager import K8sManager
from resource_manager import MinecraftServerManager

# 환경변수 로드
load_dotenv()

# FastAPI 앱 생성
app = FastAPI(
    title="Minecraft K8s Manager API",
    description="Lambda와 Kubernetes를 연결하는 중간 API 서버",
    version="2.0.0"
)

# Kubernetes 및 서버 매니저 초기화
k8s = K8sManager()
server_manager = MinecraftServerManager(k8s)

# ===== 요청 모델 =====

class CreateServerRequest(BaseModel):
    """서버 생성 요청 모델"""
    pod_name: str = Field(..., description="생성할 Pod의 이름. Kubernetes 명명 규칙에 맞게 자동으로 정규화됩니다. (예: my-first-server)")
    pvc_name: str = Field(..., description="사용할 PVC의 이름. 기존 PVC가 있으면 재사용되고, 없으면 이 이름으로 새로 생성됩니다. (예: my-server-data)")
    servertap_key: str = Field(..., description="서버 관리용 ServerTap API 키")
    memory_limit: str = Field("4Gi", description="메모리 제한 (예: 4Gi)")
    memory_request: str = Field("2Gi", description="메모리 요청 (예: 2Gi)")
    cpu_limit: str = Field("2", description="CPU 제한 (예: '2' for 2 cores)")
    cpu_request: str = Field("1", description="CPU 요청 (예: '1' for 1 core)")
    storage_capacity: str = Field("10Gi", description="PVC 스토리지 용량 (예: 10Gi)")

# ===== 헬스체크 모델 =====

class HealthResponse(BaseModel):
    """헬스체크 응답 모델"""
    status: str = Field(..., description="서버 상태")
    kubernetes: Optional[str] = Field(default="unknown", description="Kubernetes 연결 상태")

# ===== 비즈니스 로직 호출 함수 =====

def _create_server_sync(request: CreateServerRequest) -> Dict[str, Any]:
    """서버 생성 로직 (resource_manager 호출)"""
    return server_manager.create_server(
        pod_name=request.pod_name,
        pvc_name=request.pvc_name,
        servertap_key=request.servertap_key,
        memory_limit=request.memory_limit,
        memory_request=request.memory_request,
        cpu_limit=request.cpu_limit,
        cpu_request=request.cpu_request,
        storage_capacity=request.storage_capacity
    )

def _delete_server_sync(pod_name: str, pvc_name: str) -> Dict[str, Any]:
    """서버 전체 삭제 로직 (resource_manager 호출)"""
    return server_manager.delete_server(pod_name=pod_name, pvc_name=pvc_name)

def _list_volumes_sync() -> List[Dict[str, Any]]:
    """모든 데이터 볼륨 목록 조회 로직"""
    return server_manager.list_all_servers_data()

def _delete_volume_sync(pvc_name: str) -> Dict[str, Any]:
    """데이터 볼륨 영구 삭제 로직"""
    return server_manager.delete_server_data(pvc_name=pvc_name)

def _health_check_sync() -> HealthResponse:
    """헬스체크 로직"""
    result = k8s.check_connection()
    return HealthResponse(**result)

# ===== API Endpoints =====

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="헬스체크",
    description="FastAPI 서버 및 Kubernetes 연결 상태를 확인합니다."
)
def health_check() -> HealthResponse:
    """헬스체크 엔드포인트"""
    return _health_check_sync()

@app.post(
    "/k8s/server",
    summary="마인크래프트 서버 생성",
    description="Pod, PVC, Service 등 마인크래프트 서버에 필요한 모든 리소스를 생성합니다. 기존 PVC가 있으면 재사용합니다.",
    dependencies=[Depends(verify_api_key)]
)
def create_server(request: CreateServerRequest) -> Dict[str, Any]:
    """서버 생성 엔드포인트"""
    try:
        return _create_server_sync(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.delete(
    "/k8s/server/{pod_name}/{pvc_name}",
    summary="마인크래프트 서버 전체 삭제",
    description="서버 Pod 및 관련 리소스와 영구 데이터(PV/PVC)까지 모두 삭제합니다. 이 작업은 되돌릴 수 없습니다.",
    dependencies=[Depends(verify_api_key)]
)
def delete_server(pod_name: str, pvc_name: str) -> Dict[str, Any]:
    """서버 전체 삭제 엔드포인트"""
    try:
        return _delete_server_sync(pod_name, pvc_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post(
    "/k8s/server/{pod_name}/pause",
    summary="마인크래프트 서버 일시정지",
    description="서버를 일시정지 상태로 만듭니다. Pod, Deployment 등은 삭제되지만 데이터 볼륨(PVC)은 보존되어 나중에 서버를 다시 시작할 수 있습니다.",
    dependencies=[Depends(verify_api_key)]
)
def pause_server(pod_name: str) -> Dict[str, Any]:
    """서버 일시정지 엔드포인트"""
    try:
        # MinecraftServerManager의 pause_server 메소드를 직접 호출
        return server_manager.pause_server(pod_name=pod_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get(
    "/k8s/volumes",
    summary="모든 데이터 볼륨 목록 조회",
    description="이 시스템에서 관리하는 모든 서버의 데이터 볼륨(PVC) 정보를 조회합니다.",
    dependencies=[Depends(verify_api_key)]
)
def list_volumes() -> List[Dict[str, Any]]:
    """데이터 볼륨 목록 조회 엔드포인트"""
    try:
        return _list_volumes_sync()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.delete(
    "/k8s/volume/{pvc_name}",
    summary="데이터 볼륨 영구 삭제",
    description="특정 서버의 데이터(PV/PVC)만 영구적으로 삭제합니다. Pod 등 다른 리소스는 별도로 삭제해야 합니다.",
    dependencies=[Depends(verify_api_key)]
)
def delete_volume(pvc_name: str) -> Dict[str, Any]:
    """데이터 볼륨 영구 삭제 엔드포인트"""
    try:
        return _delete_volume_sync(pvc_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# ===== 시작/종료 이벤트 =====

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 실행"""
    print("=" * 50)
    print("🚀 Minecraft K8s Manager API v2.0 시작")
    print("=" * 50)
    print(f"📍 GAME_DOMAIN: {os.getenv('GAME_DOMAIN')}")
    print(f"📍 K8S_NAMESPACE: {os.getenv('K8S_NAMESPACE')}")
    print("=" * 50)
    try:
        health = health_check()
        print(f"🔍 Health check result: {health}")  # 추가
        if health.status == "healthy":
            print("✅ Kubernetes 연결 성공")
        else:
            print(f"❌ Kubernetes 연결 실패: {health.kubernetes}")
    except Exception as e:
        print(f"❌ Kubernetes 연결 실패 - Exception Type: {type(e).__name__}")  # 수정
        print(f"❌ Kubernetes 연결 실패 - Error: {str(e)}")  # 수정
        import traceback
        traceback.print_exc()  # 추가: 전체 스택 트레이스 출력
    print("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 실행"""
    print("=" * 50)
    print("🛑 Minecraft K8s Manager API 종료")
    print("=" * 50)

# ===== 루트 엔드포인트 =====

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Minecraft K8s Manager API",
        "version": "2.0.0",
        "docs": "/docs"
    }

