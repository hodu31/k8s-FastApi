# FastAPI 서버 배포 가이드

이 문서는 FastAPI 애플리케이션을 Docker 이미지로 빌드하고 Kubernetes 클러스터에 배포하는 전체 과정을 안내합니다.

## 사전 준비 사항

1.  **Docker 설치:** 로컬 컴퓨터에 Docker가 설치되어 있어야 합니다.
2.  **kubectl 설치 및 설정:** 배포할 Kubernetes 클러스터에 접근할 수 있도록 `kubectl`이 설치 및 설정되어 있어야 합니다. (`kubectl config get-contexts`로 확인)
3.  **Docker Hub 계정:** Docker 이미지를 업로드할 Docker Hub 계정이 필요합니다.

---

## 1단계: API 키 설정

배포 전, API 서버를 보호하기 위한 안전한 API 키를 설정해야 합니다.

1.  아래 명령어를 Powershell에서 실행하여 원하는 비밀 키의 `base64` 인코딩 값을 생성합니다.
    ```
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RNGCryptoServiceProvider]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes)
    ```

2.  `kubernetes/secrets.yaml` 파일을 열고, `api-key`의 값을 위에서 생성된 `base64` 인코딩 값으로 교체합니다.
    ```yaml
    # kubernetes/secrets.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: fastapi-secrets
      namespace: minecraft-servers
    type: Opaque
    data:
      # 이 값을 위에서 생성한 base64 인코딩 값으로 교체하세요.
      api-key: eW91ci1zdXBlci1zZWNyZXQtYXBpLWtleQ== 
    ```

---

## 2단계: Docker 이미지 빌드 및 푸시

FastAPI 애플리케이션을 Docker 이미지로 만들어 원격 저장소(Docker Hub)에 업로드합니다.

1.  프로젝트 루트 디렉토리에서 아래 명령어를 실행하여 Docker 이미지를 빌드합니다.
    *   `your-dockerhub-id`는 본인의 Docker Hub ID로 변경하세요.
    *   `minecraft-fastapi`는 원하는 이미지 이름으로 변경 가능합니다.
    ```sh
    docker build -t your-dockerhub-id/minecraft-fastapi:v2 .
    docker build -t de31/minecraft-fastapi:v2 .
    ```

2.  Docker Hub에 로그인합니다.
    ```sh
    docker login
    ```

3.  빌드한 이미지를 Docker Hub에 업로드(push)합니다.
    ```sh
    docker push your-dockerhub-id/minecraft-fastapi:v2
    docker push de31/minecraft-fastapi:v2
    ```

---

## 3단계: Kubernetes 배포 파일 수정

Kubernetes가 방금 업로드한 이미지를 사용하도록 배포 파일을 수정합니다.

1.  `kubernetes/fastapi-deployment.yaml` 파일을 엽니다.

2.  `spec.template.spec.containers` 아래의 `image` 경로를 2단계에서 푸시한 이미지의 전체 주소로 변경합니다.
    ```yaml
    # kubernetes/fastapi-deployment.yaml
    ...
          containers:
            - name: fastapi
              # TODO: 아래 이미지 경로는 실제 푸시한 이미지 경로로 변경해야 합니다.
              image: your-dockerhub-id/minecraft-fastapi:v2
    ...
    ```

---

## 4단계: Kubernetes에 배포

이제 모든 준비가 완료되었습니다. 아래 `kubectl` 명령어를 터미널에서 순서대로 실행하여 클러스터에 리소스를 배포합니다.

1.  **Secret 배포:**
    ```sh
    kubectl apply -f kubernetes/secrets.yaml
    ```

2.  **RBAC (권한) 배포:**
    ```sh
    kubectl apply -f kubernetes/fastapi-rbac.yaml
    ```

3.  **FastAPI 서버 배포:**
    ```sh
    kubectl apply -f kubernetes/fastapi-deployment.yaml
    ```

---

## 5단계: 배포 확인

배포가 성공적으로 완료되었는지 확인합니다.

1.  FastAPI Pod들이 정상적으로 실행 중인지 확인합니다. (`STATUS`가 `Running`으로 표시되어야 합니다.)
    ```sh
    kubectl get pods -n minecraft-servers -l app=fastapi
    ```
    **예상 출력:**
    ```
    NAME                                READY   STATUS    RESTARTS   AGE
    fastapi-deployment-5f8b6c9d8-abcde   1/1     Running   0          1m
    fastapi-deployment-5f8b6c9d8-fghij   1/1     Running   0          1m
    fastapi-deployment-5f8b6c9d8-klmno   1/1     Running   0          1m
    ```

2.  Pod의 로그를 확인하여 에러가 없는지 확인합니다. (`<pod-name>` 부분은 위에서 확인한 실제 Pod 이름으로 변경)
    ```sh
    kubectl logs -n minecraft-servers <pod-name>
    kubectl logs -n minecraft-servers fastapi-deployment-687b44d559-7sr9c
    ```
    로그 마지막에 아래와 같은 메시지가 보이면 성공입니다.
    ```
    ...
    🚀 Minecraft K8s Manager API v2.0 시작
    ==================================================
    📍 GAME_DOMAIN: mc.msdca.shop
    📍 K8S_NAMESPACE: minecraft-servers
    ==================================================
    ✅ Kubernetes 연결 성공
    ==================================================
    ...
    ```

이제 배포가 완료되었으며, `fastapi-service`의 `NodePort`(30800)를 통해 API 서버에 접근할 수 있습니다.
