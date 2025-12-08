### **Minecraft K8s Manager API 명세 (v2.0)**

이 API 서버는 Lambda와 Kubernetes를 연결하는 중간 API 서버 역할을 하며, 마인크래프트 서버 Pod 및 관련 리소스의 생성, 삭제, 그리고 데이터 볼륨 관리를 담당합니다.

**기본 URL:** `http://api.msdca.shop'

---

#### **1. 루트 엔드포인트**

*   **HTTP 메서드:** `GET`
*   **경로:** `/`
*   **요약:** API 기본 정보 제공
*   **설명:** API 서버의 버전과 설명서 경로를 안내합니다.
*   **응답:**
    ```json
    {
      "message": "Minecraft K8s Manager API",
      "version": "2.0.0",
      "docs": "/docs"
    }
    ```

---

#### **2. 헬스체크**

*   **HTTP 메서드:** `GET`
*   **경로:** `/health`
*   **요약:** FastAPI 서버 및 Kubernetes 연결 상태 확인
*   **설명:** API 서버 자체의 동작 상태와 Kubernetes 클러스터와의 연결 상태를 점검합니다.
*   **응답:** `HealthResponse` 모델
    ```json
    {
      "status": "healthy",       // 또는 "unhealthy"
      "kubernetes": "connected"  // 또는 "error: [에러 메시지]"
    }
    ```

---

#### **3. 마인크래프트 서버 생성**

*   **HTTP 메서드:** `POST`
*   **경로:** `/k8s/server`
*   **요약:** 마인크래프트 서버 및 관련 리소스 생성
*   **설명:** 새로운 마인크래프트 서버 Pod와 PersistentVolume(PV), PersistentVolumeClaim(PVC), Service, Ingress 등 필요한 모든 Kubernetes 리소스를 생성합니다. **`pvc_name`에 해당하는 PVC가 이미 존재하면 데이터를 재사용합니다.**
*   **인증:** `X-API-Key` 헤더에 유효한 API 키 필요
*   **요청 본문 (JSON):** `CreateServerRequest` 모델
    *   `pod_name` (string, 필수): 생성할 Pod의 이름. Kubernetes 명명 규칙에 맞게 자동으로 정규화됩니다. (예: `my-first-server`)
    *   `pvc_name` (string, 필수): 사용할 PVC의 이름. 기존 PVC가 있으면 재사용되고, 없으면 이 이름으로 새로 생성됩니다. (예: `my-server-data`)
    *   `servertap_key` (string, 필수): 서버 관리용 ServerTap API 키
    *   `memory_limit` (string, 선택): Pod에 할당할 메모리 제한 (예: `4Gi`). 기본값은 `4Gi`입니다.
    *   `memory_request` (string, 선택): Pod가 요청할 메모리 양 (예: `2Gi`). 기본값은 `2Gi`입니다.
    *   `cpu_limit` (string, 선택): Pod에 할당할 CPU 제한 (예: `2` for 2 cores). 기본값은 `2`입니다.
    *   `cpu_request` (string, 선택): Pod가 요청할 CPU 양 (예: `1` for 1 core). 기본값은 `1`입니다.
    ```json
    {
      "pod_name": "my-first-server",
      "pvc_name": "my-server-data",
      "servertap_key": "your-secret-servertap-key",
      "memory_limit": "4Gi",
      "memory_request": "2Gi",
      "cpu_limit": "2",
      "cpu_request": "1"
    }
    ```
*   **응답 (JSON):**
    ```json
    {
      "status": "success",
      "pod_name": "my-first-server",
      "pvc_name": "my-server-data",
      "game_url": "my-first-server.mc.msdca.shop",
      "api_url": "http://my-first-server-api.mc.msdca.shop"
    }
    ```
*   **오류:** 서버 생성 실패 시 `HTTP 500 Internal Server Error` 반환

---

#### **4. 마인크래프트 서버 전체 삭제**

*   **HTTP 메서드:** `DELETE`
*   **경로:** `/k8s/server/{pod_name}/{pvc_name}`
*   **요약:** 마인크래프트 서버의 모든 리소스(영구 데이터 포함)를 삭제합니다.
*   **설명:** 지정된 `pod_name`과 `pvc_name`에 해당하는 마인크래프트 서버의 모든 리소스(Pod, Service, Ingress, PV, PVC 등)를 영구적으로 삭제합니다. **이 작업은 되돌릴 수 없습니다.**
*   **인증:** `X-API-Key` 헤더에 유효한 API 키 필요
*   **경로 파라미터:**
    *   `pod_name` (string, 필수): 삭제할 서버의 Pod 이름
    *   `pvc_name` (string, 필수): 삭제할 서버의 PVC 이름
*   **응답 (JSON):**
    ```json
    {
        "status": "cleaned",
        "pod_name": "my-first-server",
        "pvc_name": "my-server-data"
    }
    ```
*   **오류:** 삭제 실패 시 `HTTP 500 Internal Server Error` 반환

---

#### **5. 모든 데이터 볼륨 목록 조회**

*   **HTTP 메서드:** `GET`
*   **경로:** `/k8s/volumes`
*   **요약:** 이 시스템에서 관리하는 모든 서버의 데이터 볼륨(PVC) 정보를 조회합니다.
*   **설명:** 현재 시스템에 의해 관리되고 있는 모든 마인크래프트 서버의 영구 데이터 볼륨(PersistentVolumeClaim) 목록과 상태를 반환합니다.
*   **인증:** `X-API-Key` 헤더에 유효한 API 키 필요
*   **응답 (JSON 배열):**
    ```json
    [
      {
        "name": "my-server-data",
        "namespace": "minecraft-servers",
        "creation_timestamp": "2023-10-27T10:00:00Z",
        "status": "Bound",
        "capacity": "10Gi"
      }
    ]
    ```
*   **오류:** 조회 실패 시 `HTTP 500 Internal Server Error` 반환

---

#### **6. 데이터 볼륨 영구 삭제**

*   **HTTP 메서드:** `DELETE`
*   **경로:** `/k8s/volume/{pvc_name}`
*   **요약:** 특정 서버의 데이터(PV/PVC)만 영구적으로 삭제합니다.
*   **설명:** 지정된 `pvc_name`에 해당하는 영구 데이터(PersistentVolume 및 PersistentVolumeClaim)만 삭제합니다. **Pod 등 다른 리소스는 삭제되지 않습니다. 이 작업은 되돌릴 수 없으므로 신중하게 사용해야 합니다.**
*   **인증:** `X-API-Key` 헤더에 유효한 API 키 필요
*   **경로 파라미터:**
    *   `pvc_name` (string, 필수): 데이터를 영구 삭제할 PVC의 이름
*   **응답 (JSON):**
    ```json
    {
      "status": "persistent_data_deleted",
      "pvc_name": "my-server-data"
    }
    ```
*   **오류:** 데이터 삭제 실패 시 `HTTP 500 Internal Server Error` 반환

---