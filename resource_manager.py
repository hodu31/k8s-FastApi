"""
마인크래프트 서버를 위한 고수준 리소스 관리자입니다.
이 모듈은 단일 마인크래프트 서버와 관련된 모든 쿠버네티스 리소스의 생성 및 삭제 비즈니스 로직을 처리합니다.
"""

from typing import List, Dict, Any
from k8s_manager import K8sManager

class MinecraftServerManager:
    """마인크래프트 서버와 관련 리소스의 생명주기를 관리합니다."""

    def __init__(self, k8s_manager: K8sManager):
        self.k8s = k8s_manager

    def create_server(self, pod_name: str, pvc_name: str, servertap_key: str, memory_limit: str, memory_request: str, cpu_limit: str, cpu_request: str, storage_capacity: str) -> dict:
        """
        새로운 마인크래프트 서버를 위한 전체 리소스 모음을 생성합니다.
        실패 시 k8s_manager의 cleanup_ephemeral_resources가 부분적으로 생성된 리소스를 정리합니다.
        """
        print(f"🚀 서버 생성 시작: pod={pod_name}, pvc={pvc_name}")
        
        try:
            result = self.k8s.create_minecraft_resources(
                pod_name=pod_name,
                pvc_name=pvc_name,
                servertap_api_key=servertap_key,
                memory_limit=memory_limit,
                memory_request=memory_request,
                cpu_limit=cpu_limit,
                cpu_request=cpu_request,
                storage_capacity=storage_capacity
            )
            print(f"✅ 서버 생성 완료: {pod_name}")
            return result
        except Exception as e:
            print(f"❌ 서버 생성 실패: {pod_name}. 에러: {e}")
            # 실패 시 생성된 임시 리소스를 정리합니다. PV/PVC는 유지됩니다.
            print(f"🔄 실패로 인한 임시 리소스 정리 시작: {pod_name}")
            self.k8s.cleanup_ephemeral_resources(pod_name)
            print(f"🔄 임시 리소스 정리 완료: {pod_name}")
            # API 엔드포인트에서 처리할 수 있도록 원래 예외를 다시 발생시킵니다.
            raise e

    def delete_server(self, pod_name: str, pvc_name: str) -> dict:
        """마인크래프트 서버와 관련된 모든 리소스(영구 데이터 포함)를 삭제합니다."""
        print(f"🔥 전체 서버 삭제 시작: pod={pod_name}, pvc={pvc_name}")
        try:
            result = self.k8s.cleanup_all_resources(pod_name=pod_name, pvc_name=pvc_name)
            print(f"✅ 전체 서버 삭제 완료: {pod_name}")
            return result
        except Exception as e:
            print(f"❌ 전체 서버 삭제 실패: {e}")
            raise e

    def list_all_servers_data(self) -> List[Dict[str, Any]]:
        """모든 마인크래프트 서버의 데이터 볼륨(PVC) 목록을 조회합니다."""
        print("📊 모든 서버 데이터 볼륨 목록 조회 중...")
        # 'type=minecraft-storage' 레이블을 사용하여 이 애플리케이션이 관리하는 PVC만 필터링합니다.
        return self.k8s.list_persistent_volume_claims(label_selector="type=minecraft-storage")

    def delete_server_data(self, pvc_name: str) -> Dict[str, Any]:
        """특정 마인크래프트 서버의 영구 데이터(PV/PVC)를 삭제합니다."""
        print(f"🔥 서버 데이터 영구 삭제 시작: {pvc_name}")
        self.k8s.delete_persistent_data(pvc_name=pvc_name)
        return {"status": "persistent_data_deleted", "pvc_name": pvc_name}
