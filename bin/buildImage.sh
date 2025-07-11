#!/bin/bash

SCRIPT_DIR=$(dirname "$(realpath "$0")")

DOCKERFILE_DIR="$SCRIPT_DIR/.."

docker build -t sandbox-image:latest "$DOCKERFILE_DIR"

# push to azure acr
echo "push to acr"

# az acr login -n kimitest2


docker tag sandbox-image:latest kimitest2.azurecr.io/sandbox-image:latest
docker push kimitest2.azurecr.io/sandbox-image:latest

if [[ $? != 0 ]]; then
  echo "Error: Docker build failed"
  exit 1
fi
