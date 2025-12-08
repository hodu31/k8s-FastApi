# Velocity 설정 가이드


## 🚀 빠른 배포

### 1. 네임스페이스 생성
```bash
kubectl create namespace minecraft-servers
```

### 2. 테스트용 마인클래프트 생성
example-minecraft-server.yaml 하나하나 다 생성

### 2. RBAC 적용

kubectl apply -f velocity-rbac.yaml


### 3. ConfigMap 생성

kubectl apply -f custom-plugins-config.yaml
kubectl apply -f velocity-configmap.yaml


### 4. Velocity 배포

kubectl apply -f velocity-deployment.yaml
kubectl apply -f velocity-service.yaml


### 5. 상태 확인
```bash
# Pod 상태 확인
kubectl get pods -n minecraft

# 로그 확인
kubectl logs -f deployment/velocity -n minecraft-servers


## 📊 현재 사용 중인 이미지

| 컴포넌트 | 이미지 | 버전 |
|---------|--------|------|
| Velocity | `itzg/bungeecord` | java17 |
| Minecraft 서버 | `itzg/minecraft-server` | java21 |
| Curl (initContainer) | `curlimages/curl` | latest |
