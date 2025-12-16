"""
Kubernetes 리소스 관리 모듈 (리팩토링 버전)
Pod, Service, Ingress, ConfigMap 생성/삭제 및 관련 로직을 포함합니다.
"""

from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
from dotenv import load_dotenv
from typing import Dict, Any, List
import threading
import re
import time

# --- 상수 정의 ---
load_dotenv()
NFS_BASE_PATH = os.getenv("NFS_BASE_PATH", "/mnt/nfs-minecraft")
NFS_SERVER = os.getenv("NFS_SERVER", "100.75.219.111")
GAME_DOMAIN = os.getenv("GAME_DOMAIN", "mc.msdca.shop")
K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "minecraft-servers")
MINECRAFT_IMAGE = os.getenv("MINECRAFT_IMAGE", "itzg/minecraft-server:latest")
BUSYBOX_IMAGE = os.getenv("BUSYBOX_IMAGE", "busybox:1.35")
DEFAULT_STORAGE_CAPACITY = os.getenv("DEFAULT_STORAGE_CAPACITY", "10Gi")
MEMORY_LIMIT = os.getenv("MEMORY_LIMIT", "3Gi")
MEMORY_REQUEST = os.getenv("MEMORY_REQUEST", "3Gi")
CPU_LIMIT = os.getenv("CPU_LIMIT", "2")
CPU_REQUEST = os.getenv("CPU_REQUEST", "2")
VELOCITY_SECRET = os.getenv("VELOCITY_SECRET")
if not VELOCITY_SECRET:
    raise RuntimeError("VELOCITY_SECRET 환경변수가 설정되지 않았습니다!")

class K8sManager:
    """Kubernetes 리소스 관리 클래스"""

    def __init__(self):
        """Kubernetes 클라이언트 초기화"""
        try:
            try:
                config.load_incluster_config()
                print("✅ In-cluster Kubernetes config 로드 성공")
            except config.ConfigException:
                config.load_kube_config()
                print("✅ Local kubeconfig 로드 성공")
            
            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.networking_v1 = client.NetworkingV1Api()
            self.batch_v1 = client.BatchV1Api()
            self._configmap_lock = threading.Lock()
            
            print("✅ Kubernetes 클라이언트 초기화 완료")
        except Exception as e:
            print(f"❌ Kubernetes 클라이언트 초기화 실패: {e}")
            raise

    def _sanitize_name(self, name: str) -> str:
        """Kubernetes 리소스 이름으로 사용할 수 있도록 문자열을 정규화합니다."""
        sanitized = re.sub(r'[^a-z0-9-]', '', name.lower())
        sanitized = sanitized.strip('-')
        sanitized = re.sub(r'-+', '-', sanitized)
        if sanitized != name:
            print(f"🔧 이름 정규화: '{name}' → '{sanitized}'")
        return sanitized

    def pvc_exists(self, pvc_name: str) -> bool:
        """주어진 이름의 PVC가 존재하는지 확인합니다."""
        try:
            self.v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=K8S_NAMESPACE)
            print(f"🔍 PVC '{pvc_name}'이(가) 이미 존재합니다.")
            return True
        except ApiException as e:
            if e.status == 404:
                print(f"🔍 PVC '{pvc_name}'을(를) 찾을 수 없습니다. 새로 생성합니다.")
                return False
            print(f"❌ PVC '{pvc_name}' 확인 중 오류 발생: {e}")
            raise

    def create_persistent_volume(self, pvc_name: str, storage_capacity: str):
        """NFS PersistentVolume을 생성합니다."""
        pv_name = f"pv-{pvc_name}"
        nfs_path = f"{NFS_BASE_PATH}/{pvc_name}"
        
        # PV가 이미 존재하는지 확인
        try:
            self.v1.read_persistent_volume(name=pv_name)
            print(f"💿 PV '{pv_name}'이(가) 이미 존재하여 재생성하지 않습니다.")
            return
        except ApiException as e:
            if e.status != 404:
                raise

        pv = client.V1PersistentVolume(
            api_version="v1",
            kind="PersistentVolume",
            metadata=client.V1ObjectMeta(name=pv_name, labels={"app": pvc_name}),
            spec=client.V1PersistentVolumeSpec(
                capacity={"storage": storage_capacity},
                volume_mode="Filesystem",
                access_modes=["ReadWriteOnce"],
                persistent_volume_reclaim_policy="Retain",
                storage_class_name="manual",
                nfs=client.V1NFSVolumeSource(server=NFS_SERVER, path=nfs_path)
            )
        )
        print(f"💿 PV '{pv_name}' 생성 중...")
        self.v1.create_persistent_volume(body=pv)

    def create_persistent_volume_claim(self, pvc_name: str, storage_capacity: str):
        """PersistentVolumeClaim을 생성합니다."""
        pvc = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(name=pvc_name, namespace=K8S_NAMESPACE, labels={"app": pvc_name, "type": "minecraft-storage"}),
            spec=client.V1PersistentVolumeClaimSpec(
                storage_class_name="manual",
                access_modes=["ReadWriteOnce"],
                resources=client.V1ResourceRequirements(requests={"storage": storage_capacity}),
                volume_name=f"pv-{pvc_name}"
            )
        )
        print(f"💿 PVC '{pvc_name}' 생성 중...")
        self.v1.create_namespaced_persistent_volume_claim(namespace=K8S_NAMESPACE, body=pvc)
        self._wait_for_pvc_bound(pvc_name)

    def _wait_for_pvc_bound(self, pvc_name: str, timeout: int = 60):
        """PVC가 'Bound' 상태가 될 때까지 기다립니다."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                pvc = self.v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=K8S_NAMESPACE)
                if pvc.status.phase == "Bound":
                    print(f"✅ PVC '{pvc_name}' 바인딩 완료!")
                    return
            except ApiException as e:
                if e.status == 404:
                    # PVC가 생성되는 도중에 조회를 시도하면 404가 발생할 수 있음
                    pass
                else:
                    raise
            time.sleep(2)
        raise Exception(f"PVC {pvc_name} 바인딩 타임아웃")

    def create_or_update_paper_configmap(self):
        """Velocity 연동을 위한 paper-global.yml ConfigMap을 생성하거나 업데이트합니다."""
        cm_name = "paper-global-config"
        config_data = {
            "paper-global.yml": f"""
proxies:
  velocity:
    enabled: true
    online-mode: false
    secret: '{VELOCITY_SECRET}'
"""
        }
        
        try:
            self.v1.read_namespaced_config_map(name=cm_name, namespace=K8S_NAMESPACE)
            print(f"📜 ConfigMap '{cm_name}'이(가) 이미 존재합니다. 업데이트를 시도합니다.")
            self.v1.patch_namespaced_config_map(name=cm_name, namespace=K8S_NAMESPACE, body={"data": config_data})
        except ApiException as e:
            if e.status == 404:
                cm = client.V1ConfigMap(
                    api_version="v1",
                    kind="ConfigMap",
                    metadata=client.V1ObjectMeta(name=cm_name, namespace=K8S_NAMESPACE),
                    data=config_data
                )
                print(f"📜 ConfigMap '{cm_name}' 생성 중...")
                self.v1.create_namespaced_config_map(namespace=K8S_NAMESPACE, body=cm)
            else:
                raise

    def create_servertap_configmap(self, pod_name: str, api_key: str):
        """ServerTap을 위한 ConfigMap을 생성합니다."""
        cm_name = f"servertap-config-{pod_name}"
        config_data = {
            "config.yml": f"""
port: 4567
debug: false
useKeyAuth: true
key: {api_key}
normalizeMessages: true
tls:
  enabled: false
corsOrigins:
  - "*"
websocketConsoleBuffer: 1000
disable-swagger: false
blocked-paths: []
"""
        }
        cm = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(name=cm_name, namespace=K8S_NAMESPACE),
            data=config_data
        )
        print(f"📜 ConfigMap '{cm_name}' 생성 중...")
        self.v1.create_namespaced_config_map(namespace=K8S_NAMESPACE, body=cm)

    def create_deployment(self, deployment_name: str, pvc_name: str, memory_limit: str = MEMORY_LIMIT, memory_request: str = MEMORY_REQUEST, cpu_limit: str = CPU_LIMIT, cpu_request: str = CPU_REQUEST):
        """마인크래프트 서버를 위한 Deployment를 생성합니다."""
        pod_labels = {"app": deployment_name, "type": "minecraft-server"}

        pod_spec = client.V1PodSpec(
            priority_class_name="high-priority-customer",
            init_containers=[
                client.V1Container(
                    name="copy-plugins-from-cache",
                    image=BUSYBOX_IMAGE,
                    command=['sh', '-c'],
                    args=[
                        "set -e; "
                        "mkdir -p /data/plugins; "
                        "cp /plugins-cache/*.jar /data/plugins/ 2>/dev/null || true; "
                        "chmod 644 /data/plugins/*.jar 2>/dev/null || true; "
                        "echo 'Plugins copied from cache:'; "
                        "ls -lh /data/plugins/"
                    ],
                    volume_mounts=[
                        client.V1VolumeMount(name="minecraft-data", mount_path="/data"),
                        client.V1VolumeMount(name="plugins-cache", mount_path="/plugins-cache", read_only=True)
                    ],
                    security_context=client.V1SecurityContext(run_as_user=1000, run_as_group=1000)
                ),
                client.V1Container(
                    name="copy-servertap-config",
                    image=BUSYBOX_IMAGE,
                    command=['sh', '-c'],
                    args=[
                        "set -e; mkdir -p /data/plugins/ServerTap; "
                        f"cp /config/config.yml /data/plugins/ServerTap/config.yml; "
                        "chmod 644 /data/plugins/ServerTap/config.yml; "
                        "echo 'ServerTap config copied successfully.'"
                    ],
                    volume_mounts=[
                        client.V1VolumeMount(name="minecraft-data", mount_path="/data"),
                        client.V1VolumeMount(name="servertap-config", mount_path="/config")
                    ],
                    security_context=client.V1SecurityContext(run_as_user=1000, run_as_group=1000)
                ),
                client.V1Container(
                    name="copy-paper-config",
                    image=BUSYBOX_IMAGE,
                    command=['sh', '-c'],
                    args=[
                        "set -e; mkdir -p /data/config; "
                        "cp /paper-config/paper-global.yml /data/config/paper-global.yml; "
                        "chmod 644 /data/config/paper-global.yml; "
                        "echo 'Paper config copied successfully.'"
                    ],
                    volume_mounts=[
                        client.V1VolumeMount(name="minecraft-data", mount_path="/data"),
                        client.V1VolumeMount(name="paper-config", mount_path="/paper-config")
                    ],
                    security_context=client.V1SecurityContext(run_as_user=1000, run_as_group=1000)
                )
            ],
            containers=[
                client.V1Container(
                    name="minecraft",
                    image=MINECRAFT_IMAGE,
                    ports=[
                        client.V1ContainerPort(container_port=25565, name="minecraft"),
                        client.V1ContainerPort(container_port=4567, name="servertap")
                    ],
                    env=[
                        client.V1EnvVar(name="EULA", value="TRUE"),
                        client.V1EnvVar(name="TYPE", value="PAPER"),
                        client.V1EnvVar(name="VERSION", value="1.21.1"),
                        client.V1EnvVar(name="MEMORY", value="2G"),
                        client.V1EnvVar(name="ONLINE_MODE", value="FALSE"),
                        client.V1EnvVar(name="MAX_TICK_TIME", value="-1"),
                        client.V1EnvVar(name="PAPER_PROXY_SECRET", value=VELOCITY_SECRET),# 👇 [수정됨] Velocity 연동 필수 환경변수 3개 👇
                        client.V1EnvVar(name="CFG_PAPER_PROXIES_VELOCITY_ENABLED", value="true"),
                        client.V1EnvVar(name="CFG_PAPER_PROXIES_VELOCITY_ONLINE_MODE", value="false"),
                        # 기존 PAPER_PROXY_SECRET 대신 정확한 변수명 사용
                        client.V1EnvVar(name="CFG_PAPER_PROXIES_VELOCITY_SECRET", value=VELOCITY_SECRET),
                    ],
                    resources=client.V1ResourceRequirements(
                        limits={"cpu": str(cpu_limit), "memory": memory_limit},
                        requests={"cpu": str(cpu_request), "memory": memory_request}
                    ),
                    security_context=client.V1SecurityContext(run_as_non_root=True, run_as_user=1000, run_as_group=1000, allow_privilege_escalation=False),
                    volume_mounts=[client.V1VolumeMount(name="minecraft-data", mount_path="/data")],
                    readiness_probe=client.V1Probe(tcp_socket=client.V1TCPSocketAction(port=25565), initial_delay_seconds=60, period_seconds=5, failure_threshold=20),
                    liveness_probe=client.V1Probe(tcp_socket=client.V1TCPSocketAction(port=25565), initial_delay_seconds=180, period_seconds=30, failure_threshold=3)
                )
            ],
            volumes=[
                client.V1Volume(name="minecraft-data", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name)),
                client.V1Volume(
                    name="plugins-cache",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name="plugins-cache",
                        read_only=True
                    )
                ),
                client.V1Volume(name="servertap-config", config_map=client.V1ConfigMapVolumeSource(name=f"servertap-config-{deployment_name}")),
                client.V1Volume(name="paper-config", config_map=client.V1ConfigMapVolumeSource(name="paper-global-config"))
            ],
            security_context=client.V1PodSecurityContext(fs_group=1000, run_as_non_root=True),
            restart_policy="Always"
        )

        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=K8S_NAMESPACE,
                labels=pod_labels
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels=pod_labels),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=pod_labels),
                    spec=pod_spec
                )
            )
        )

        print(f"📦 Deployment '{deployment_name}' 생성 중...")
        self.apps_v1.create_namespaced_deployment(namespace=K8S_NAMESPACE, body=deployment)

    def create_service(self, pod_name: str):
        """Pod를 위한 ClusterIP 서비스를 생성합니다."""
        service_name = f"{pod_name}-svc"
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=service_name,
                namespace=K8S_NAMESPACE,
                labels={"app": pod_name, "minecraft-server": "true", "subdomain": pod_name}
            ),
            spec=client.V1ServiceSpec(
                selector={"app": pod_name},
                type="ClusterIP",
                ports=[
                    client.V1ServicePort(name="minecraft", port=25565, target_port=25565),
                    client.V1ServicePort(name="api", port=4567, target_port=4567)
                ]
            )
        )
        print(f"🔌 Service '{service_name}' 생성 중...")
        self.v1.create_namespaced_service(namespace=K8S_NAMESPACE, body=service)

    def create_ingress(self, pod_name: str):
        """ServerTap API를 위한 Ingress를 생성합니다."""
        ingress_name = f"servertap-{pod_name}-ingress"
        service_name = f"{pod_name}-svc"
        host = f"{pod_name}-api.{GAME_DOMAIN}"
        
        ingress = client.V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=client.V1ObjectMeta(
                name=ingress_name,
                namespace=K8S_NAMESPACE,
                annotations={
                    # "nginx.ingress.kubernetes.io/rewrite-target": "/",
                    "nginx.ingress.kubernetes.io/websocket-services": service_name
                }
            ),
            spec=client.V1IngressSpec(
                ingress_class_name="nginx",
                rules=[
                    client.V1IngressRule(
                        host=host,
                        http=client.V1HTTPIngressRuleValue(
                            paths=[
                                client.V1HTTPIngressPath(
                                    path="/",
                                    path_type="Prefix",
                                    backend=client.V1IngressBackend(
                                        service=client.V1IngressServiceBackend(
                                            name=service_name,
                                            port=client.V1ServiceBackendPort(number=4567)
                                        )
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
        print(f"🌐 Ingress '{ingress_name}' 생성 중 (Host: {host})...")
        self.networking_v1.create_namespaced_ingress(namespace=K8S_NAMESPACE, body=ingress)

    def create_minecraft_resources(self, pod_name: str, pvc_name: str, servertap_api_key: str, memory_limit: str = MEMORY_LIMIT, memory_request: str = MEMORY_REQUEST, cpu_limit: str = CPU_LIMIT, cpu_request: str = CPU_REQUEST, storage_capacity: str = DEFAULT_STORAGE_CAPACITY) -> Dict[str, Any]:
        """마인크래프트 서버에 필요한 모든 리소스를 생성/관리합니다."""
        deployment_name = self._sanitize_name(pod_name) # pod_name을 deployment_name으로 사용
        pvc_name = self._sanitize_name(pvc_name)

        # 0. 기존 임시 리소스 정리 (Deployment, Service, Ingress, ConfigMap)
        self.cleanup_ephemeral_resources(deployment_name)

        # 1. ConfigMap 생성
        self.create_or_update_paper_configmap()
        self.create_servertap_configmap(deployment_name, servertap_api_key)

        # 2. PV/PVC 생성 또는 재사용
        if not self.pvc_exists(pvc_name):
            self.create_nfs_directory_job(pvc_name)
            self.create_persistent_volume(pvc_name, storage_capacity)
            self.create_persistent_volume_claim(pvc_name, storage_capacity)
        
        # 3. Deployment 생성
        self.create_deployment(deployment_name, pvc_name, memory_limit, memory_request, cpu_limit, cpu_request)

        # 4. Service 생성
        self.create_service(deployment_name)

        # 5. Ingress 생성
        self.create_ingress(deployment_name)

        return {
            "status": "success",
            "pod_name": deployment_name,
            "pvc_name": pvc_name,
            "game_url": f"{deployment_name}.{GAME_DOMAIN}",
            "api_url": f"http://{deployment_name}-api.{GAME_DOMAIN}"
        }

    def _delete_resource(self, delete_func, resource_type: str, resource_name: str, **kwargs):
        """네임스페이스에 속한 리소스를 삭제하고 예외를 처리하는 범용 헬퍼 함수입니다."""
        try:
            delete_func(name=resource_name, namespace=K8S_NAMESPACE, **kwargs)
            print(f"✅ {resource_type} '{resource_name}' 삭제 요청됨")
        except ApiException as e:
            if e.status != 404:
                print(f"❌ {resource_type} '{resource_name}' 삭제 실패: {e.reason}")
                raise
            print(f"⚠️ {resource_type} '{resource_name}'이(가) 존재하지 않음")

    def cleanup_ephemeral_resources(self, pod_name: str):
        """Deployment, Service, Ingress 등 일시적인 리소스를 정리합니다. (PV/PVC 제외)"""
        print(f"🧹 임시 리소스 정리 시작: {pod_name}")
        self._delete_resource(self.apps_v1.delete_namespaced_deployment, "Deployment", pod_name)
        self._delete_resource(self.v1.delete_namespaced_service, "Service", f"{pod_name}-svc")
        self._delete_resource(self.networking_v1.delete_namespaced_ingress, "Ingress", f"servertap-{pod_name}-ingress")
        self._delete_resource(self.v1.delete_namespaced_config_map, "ConfigMap", f"servertap-config-{pod_name}")
        # paper-global-config는 공용이므로 삭제하지 않음
        
        # === [추가된 부분] ===
        return {
            "status": "success",
            "message": f"Server {pod_name} resources cleaned up (paused).",
            "pod_name": pod_name
        }
    def delete_persistent_data(self, pvc_name: str):
        """영구 데이터(PVC 및 PV)를 삭제합니다."""
        pvc_name = self._sanitize_name(pvc_name)
        print(f"🔥 영구 데이터 삭제 시작: {pvc_name}")
        self._delete_resource(self.v1.delete_namespaced_persistent_volume_claim, "PVC", pvc_name)
        try:
            pv_name = f"pv-{pvc_name}"
            self.v1.delete_persistent_volume(name=pv_name)
            print(f"✅ PersistentVolume '{pv_name}' 삭제 요청됨")
        except ApiException as e:
            if e.status != 404:
                print(f"❌ PersistentVolume '{pv_name}' 삭제 실패: {e.reason}")
                raise
            print(f"⚠️ PersistentVolume '{pv_name}'이(가) 존재하지 않음")

    def cleanup_all_resources(self, pod_name: str, pvc_name: str) -> Dict[str, Any]:
        """주어진 이름과 관련된 모든 리소스를 삭제합니다."""
        pod_name = self._sanitize_name(pod_name)
        pvc_name = self._sanitize_name(pvc_name)
        print(f"🧹 전체 리소스 정리 시작: pod={pod_name}, pvc={pvc_name}")
        
        self.cleanup_ephemeral_resources(pod_name)
        self.delete_persistent_data(pvc_name)

        print(f"✅ 전체 리소스 정리 완료: {pod_name}")
        return {"status": "cleaned", "pod_name": pod_name, "pvc_name": pvc_name}

    def list_persistent_volume_claims(self, label_selector: str) -> List[Dict[str, Any]]:
        """레이블 셀렉터와 일치하는 네임스페이스의 모든 PVC 목록을 반환합니다."""
        pvcs = self.v1.list_namespaced_persistent_volume_claim(
            namespace=K8S_NAMESPACE,
            label_selector=label_selector
        )
        
        pvc_list = []
        for pvc in pvcs.items:
            pvc_list.append({
                "name": pvc.metadata.name,
                "namespace": pvc.metadata.namespace,
                "creation_timestamp": pvc.metadata.creation_timestamp.isoformat(),
                "status": pvc.status.phase,
                "capacity": pvc.status.capacity.get("storage") if pvc.status.capacity else "N/A"
            })
        return pvc_list

    def check_connection(self) -> Dict[str, str]:
        """Kubernetes API 서버와의 연결을 확인합니다."""
        try:
            # 클러스터 전체가 아닌, 자신이 속한 네임스페이스의 리소스를 조회하여 연결을 확인합니다.
            self.v1.list_namespaced_pod(namespace=K8S_NAMESPACE, limit=1)
            return {"status": "healthy", "kubernetes": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "kubernetes": f"error: {str(e)}"}
        
        
    def create_nfs_directory_job(self, pvc_name: str):
        """NFS 서버에 디렉토리를 생성하는 Job을 실행합니다."""
        job_name = f"create-nfs-dir-{pvc_name}"
        nfs_path = f"{NFS_BASE_PATH}/{pvc_name}"
        
        # 기존 Job이 있다면 삭제
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=K8S_NAMESPACE,
                propagation_policy='Background'
            )
            print(f"🗑️ 기존 Job '{job_name}' 삭제 중...")
            time.sleep(2)
        except ApiException as e:
            if e.status != 404:
                raise
        
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=K8S_NAMESPACE
            ),
            spec=client.V1JobSpec(
                ttl_seconds_after_finished=60,
                backoff_limit=3,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels={"job": job_name}
                    ),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="nfs-dir-creator",
                                image=BUSYBOX_IMAGE,
                                command=['sh', '-c'],
                                args=[
                                    f"mkdir -p {nfs_path} && "
                                    f"chmod 755 {nfs_path} && "
                                    f"chown 1000:1000 {nfs_path} && "  # Minecraft 서버 UID/GID
                                    f"echo 'Directory created: {nfs_path}'"
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="nfs-root",
                                        mount_path=NFS_BASE_PATH
                                    )
                                ]
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="nfs-root",
                                nfs=client.V1NFSVolumeSource(
                                    server=NFS_SERVER,
                                    path=NFS_BASE_PATH
                                )
                            )
                        ],
                        restart_policy="Never"
                    )
                )
            )
        )
        
        print(f"📁 NFS 디렉토리 생성 Job '{job_name}' 실행 중...")
        self.batch_v1.create_namespaced_job(namespace=K8S_NAMESPACE, body=job)
        self._wait_for_job_completion(job_name)

    def _wait_for_job_completion(self, job_name: str, timeout: int = 60):
        """Job이 완료될 때까지 대기합니다."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                job = self.batch_v1.read_namespaced_job(
                    name=job_name,
                    namespace=K8S_NAMESPACE
                )
                
                if job.status.succeeded:
                    print(f"✅ Job '{job_name}' 완료!")
                    return
                
                if job.status.failed:
                    # Job 실패 시 로그 출력
                    pods = self.v1.list_namespaced_pod(
                        namespace=K8S_NAMESPACE,
                        label_selector=f"job-name={job_name}"
                    )
                    if pods.items:
                        pod_name = pods.items[0].metadata.name
                        logs = self.v1.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=K8S_NAMESPACE
                        )
                        print(f"❌ Job 로그:\n{logs}")
                    raise Exception(f"Job '{job_name}' 실패!")
                    
            except ApiException as e:
                if e.status != 404:
                    raise
            
            time.sleep(2)
        
        raise Exception(f"Job '{job_name}' 타임아웃 (60초 초과)")