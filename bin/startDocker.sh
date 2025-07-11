#!/bin/bash

IMAGE_NAME="sandbox-image"
CONTAINER_NAME="sandbox-container"
PORT_MAPPING="8000:8000"

if ! command -v docker &> /dev/null; then
    echo "错误：Docker 未安装，请先安装 Docker。"
    exit 1
fi

# 停止并删除已存在的同名容器（如果存在）
if [ "$(sudo docker ps -a -q -f name=${CONTAINER_NAME})" ]; then
    echo "正在停止并删除已存在的容器：${CONTAINER_NAME}"
    sudo docker stop ${CONTAINER_NAME} &> /dev/null
    sudo docker rm ${CONTAINER_NAME} &> /dev/null
fi

echo "正在启动 Docker 容器：${CONTAINER_NAME}"
sudo docker run -d \
    --runtime=runsc \
    --name ${CONTAINER_NAME} \
    -p ${PORT_MAPPING} \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --memory=512m \
    --cpus=1 \
    ${IMAGE_NAME} || {
        echo "错误：Docker 容器启动失败"
        exit 1
    }

echo "容器 ${CONTAINER_NAME} 已启动，监听端口 ${PORT_MAPPING}"