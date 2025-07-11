#!/bin/bash

set -xe

SCRIPT_DIR=$(dirname "$(realpath "$0")")

ROOT_DIR="$SCRIPT_DIR/.."

# kind delete cluster

kind create cluster --config "$ROOT_DIR/k8s/kind-config.yaml"
