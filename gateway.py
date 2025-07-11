from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import asyncio
from kubernetes import client, config
from kubernetes.client.rest import ApiException
app = FastAPI()

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()
k8s_core_v1 = client.CoreV1Api()
k8s_metrics_client = client.CustomObjectsApi()

def parse_resource(resource: str) -> float:
    """将 Kubernetes 资源格式转换为数值（CPU: 核，内存: 字节）。"""

    print(f"resource {resource}")
    if not resource:
        return 0.0
    if resource.endswith("n"):  # CPU 纳核
        return float(resource[:-1]) / 1e9
    if resource.endswith("m"):  # CPU 毫核
        return float(resource[:-1]) / 1000
    if resource.endswith("Gi"):
        return float(resource[:-2]) * 1024 * 1024 * 1024
    if resource.endswith("Mi"):
        return float(resource[:-2]) * 1024 * 1024
    if resource.endswith("Ki"):
        return float(resource[:-2]) * 1024
    return float(resource)  # 原始 float 值

async def get_cluster_metrics():
    """
    获取所有节点的 CPU/Memory 使用率
    """
    try:
        # 获取节点指标
        metrics = await asyncio.to_thread(
            k8s_metrics_client.list_cluster_custom_object,
            "metrics.k8s.io", "v1beta1", "nodes"
        )

        # 获取节点容量信息
        nodes = k8s_core_v1.list_node()
        node_capacities = {
            node.metadata.name: {
                "cpu": node.status.capacity["cpu"],
                "memory": node.status.capacity["memory"]
            } for node in nodes.items
        }

        # 组合数据
        usage_data = []
        for item in metrics["items"]:
            node_name = item["metadata"]["name"]
            usage = item["usage"]
            capacity = node_capacities.get(node_name, {})

            usage_data.append({
                "node": node_name,
                "cpu": {
                    "usage": usage.get("cpu", "0"),
                    "capacity": capacity.get("cpu", "0")
                },
                "memory": {
                    "usage": usage.get("memory", "0"),
                    "capacity": capacity.get("memory", "0")
                }
            })
        print(f"usage_data is {usage_data}")
        return usage_data
    except ApiException as e:
        print(f"K8s API error: {e.reason}, Status: {e.status}, Body: {e.body}")
        raise HTTPException(status_code=500, detail=f"K8s API error: {e.reason}, Body: {e.body}")
    except Exception as e:
        print(f"Error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error details: {str(e)}")

async def can_schedule_secret_k8s():
    """
    检查所有节点的 CPU 和内存使用率是否都不超过80%
    如果所有节点都不超过80%，返回 True；否则返回 False
    """
    try:
        # 获取节点资源使用数据
        usage_data = await get_cluster_metrics()

        print(f'{len(usage_data)}')

        # 检查每个节点的使用率
        for node in usage_data:
            # 解析 CPU 使用率和容量
            cpu_usage = parse_resource(node["cpu"]["usage"])
            cpu_capacity = parse_resource(node["cpu"]["capacity"])

            # 解析内存使用率和容量
            mem_usage = parse_resource(node["memory"]["usage"])
            mem_capacity = parse_resource(node["memory"]["capacity"])

            # 计算使用率百分比（避免除以零）
            cpu_percent = (cpu_usage / cpu_capacity * 100) if cpu_capacity > 0 else 0
            mem_percent = (mem_usage / mem_capacity * 100) if mem_capacity > 0 else 0

            print(f"Node {node['node']} exceeds 80% usage: CPU={cpu_percent:.2f}%, Memory={mem_percent:.2f}%")
            if cpu_percent < 80 and mem_percent < 80:
                print(f"Node {node['node']} exceeds 80% usage: CPU={cpu_percent:.2f}%, Memory={mem_percent:.2f}%")
                return True

        # 所有节点都满足条件
        print("All nodes have resource usage below 80%")
        return True

    except Exception as e:
        # 记录错误并返回 False（保守决策）
        print(f"Error checking cluster usage: {str(e)}")
        return False

# Kubernetes Ingress base URL
K8S_LOCAL_INGRESS_URL = "http://sandbox.default.svc.cluster.local:5858"
K8S_AKS_INGRESS_URL = "http://localhost:80"

from kubernetes import client, config

pod_mapping = {}

def get_or_create_pod(sessionid: str):
    """
    根据 sessionid 获取或创建 Kubernetes Pod 配置。
    Pod 名称以 'sandbox-pod-' 开头，后接 sessionid。
    如果 pod_mapping 中存在 sessionid，则返回已有 Pod 配置；
    否则创建一个新的 Pod 配置并存储。

    Args:
        sessionid (str): 会话 ID，用于标识 Pod。

    Returns:
        dict: Kubernetes Pod 的配置。
    """
    # 检查 pod_mapping 中是否已有 sessionid 对应的 Pod
    if sessionid in pod_mapping:
        return pod_mapping[sessionid]

    pod_name = f"sandbox-pod-{sessionid}"
    # Kubernetes API 配置（假设已配置好 kubeconfig 或服务账号）

    # 定义 Pod 配置，名称为 sandbox-pod-<sessionid>
    pod_manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "labels": {
                "app": "sandbox",
                "sessionid": sessionid
            }
        },
        "spec": {
            "containers": [
                {
                    "name": "sandbox",
                    "image": "kimitest2.azurecr.io/sandbox-image:latest",
                    "imagePullPolicy": "Always",
                    "ports": [
                        {"containerPort": 8000},
                        {"containerPort": 5858}
                    ],
                    "resources": {
                        "limits": {
                            "cpu": "1",
                            "memory": "512Mi"
                        },
                        "requests": {
                            "cpu": "0.5",
                            "memory": "256Mi"
                        }
                    }
                }
            ]
        }
    }

    try:
        # 尝试创建 Pod
        namespace = "default"  # 可根据需要修改命名空间
        k8s_core_v1.create_namespaced_pod(namespace=namespace, body=pod_manifest)
        print(f"Pod created for sessionid: {sessionid}, name: sandbox-pod-{sessionid}")

        # 存储 Pod 配置到 pod_mapping
        pod_mapping[sessionid] = pod_name
        return pod_mapping[sessionid]

    except Exception as e:
        print(f"Error creating Pod for sessionid {sessionid}: {e}")
        return None


def get_local_url(pod_name: str) -> str:
    """
    根据 Pod 名称生成本地访问 URL。
    假设 Pod 运行在 Kubernetes 集群中，通过 NodePort 或 ClusterIP 服务暴露端口。

    Args:
        pod_name (str): Pod 名称，例如 'sandbox-pod-session123'。

    Returns:
        str: Pod 的本地访问 URL（例如 'http://<node-ip>:<port>' 或 'http://<cluster-ip>:<port>'）。
        如果无法获取 URL，则返回空字符串。
    """
    from kubernetes import client, config

    try:
        # 加载 Kubernetes 配置
        namespace = "default"  # 可根据需要修改命名空间
        # 如果未找到匹配的服务，尝试直接通过 Pod IP 和端口
        pod = k8s_core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        pod_ip = pod.status.pod_ip
        print(f"pod_name {pod_name} pod_ip {pod_ip}")
        if pod_ip:
            url = f"http://{pod_ip}:5858"
            return url

        return ""  # 未找到有效 URL
    except client.ApiException as e:
        print(f"Error retrieving URL for pod {pod_name}: {e}")
        return ""

client = httpx.AsyncClient()

async def get_host(sessionid):
    use_local = await can_schedule_secret_k8s()
    if use_local:
        pod_name = get_or_create_pod(sessionid)
        print(f"pod name {pod_name}")
        return get_local_url(pod_name)
    return ''

class ExecRequest(BaseModel):
    code: str

@app.get("/{sessionid}/processes")
async def get_processes(sessionid: str):
    try:
        host = await get_host(sessionid)
        print(f"url is {host}/{sessionid}/processes")
        response = await client.get(f"{host}/{sessionid}/processes")
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to get processes: {str(e)}")

@app.post("/{sessionid}/process/kill/{pid}")
async def kill_process(sessionid: str, pid: int):
    try:
        host = await get_host(sessionid)
        response = await client.post(f"{host}/{sessionid}/process/kill/{pid}")
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill process: {str(e)}")

@app.post("/{sessionid}/files/upload")
async def upload_file(sessionid: str):
    try:
        host = await get_host(sessionid)
        response = await client.post(f"{host}/{sessionid}/files/upload")
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.get("/{sessionid}/files/download/{filename}")
async def download_file(sessionid: str, filename: str):
    try:
        host = await get_host(sessionid)
        response = await client.get(f"{host}/{sessionid}/files/download/{filename}", stream=True)
        return StreamingResponse(response.aiter_raw(),
                               headers={"Content-Disposition": f"attachment; filename={filename}"})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")

@app.delete("/{sessionid}/files/delete/{filename}")
async def delete_file(sessionid: str, filename: str):
    try:
        host = await get_host(sessionid)
        response = await client.delete(f"{host}/{sessionid}/files/delete/{filename}")
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@app.post("/{sessionid}/exec/python")
async def exec_python(sessionid: str, request: ExecRequest):
    try:
        host = await get_host(sessionid)
        response = await client.post(f"{host}/{sessionid}/exec/python",
                                  json={"code": request.code})
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute python code: {str(e)}")

@app.post("/{sessionid}/exec/nodejs")
async def exec_nodejs(sessionid: str, request: ExecRequest):
    try:
        host = await get_host(sessionid)
        response = await client.post(f"{host}/{sessionid}/exec/nodejs",
                                  json={"code": request.code})
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute nodejs code: {str(e)}")