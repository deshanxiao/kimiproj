#!/bin/bash

set -xe

SCRIPT_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR="$SCRIPT_DIR/.."

# 安装 Ingress Nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 等待控制器就绪
echo "等待 Ingress-Nginx 控制器准备就绪..."
kubectl wait --namespace ingress-nginx \
  --for=condition=Ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# 等待 Webhook 服务准备就绪
echo "等待 Admission Webhook 准备就绪..."
kubectl wait --namespace ingress-nginx \
  --for=condition=Available deployment/ingress-nginx-controller \
  --timeout=120s

# 创建 metrics-server 所需的特殊权限
echo "创建 metrics-server 特殊权限..."
kubectl create rolebinding -n kube-system metrics-server-auth-reader \
  --role=extension-apiserver-authentication-reader \
  --serviceaccount=kube-system:metrics-server

# 应用 RBAC 权限（为应用）
echo "应用 Metrics API 访问权限..."
kubectl apply -f "$ROOT_DIR/k8s/metrics-rbac.yaml"

# 应用主应用配置
echo "部署应用..."
kubectl apply -f "$ROOT_DIR/k8s/deployment-local.yaml"

# 应用 Ingress 配置
kubectl apply -f "$ROOT_DIR/k8s/ingress-nginx-config.yaml"

# 配置监控
echo "部署 Metrics Server..."
kubectl apply -f "$ROOT_DIR/k8s/metrics-server.yaml"

# 等待 Metrics Server 就绪
echo "等待 Metrics Server 准备就绪..."
kubectl wait --namespace kube-system \
  --for=condition=Available deployment/metrics-server \
  --timeout=180s

# 重启应用 Pod 以刷新 ServiceAccount 令牌
echo "重启应用 Pod 以应用新权限..."
kubectl delete pod -l app=sandbox --wait=false

echo "部署完成！"