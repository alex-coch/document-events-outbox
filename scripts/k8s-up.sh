#!/bin/sh
set -eu
mkdir -p .demo
export KUBECONFIG="$PWD/.demo/kubeconfig"
cluster=outbox-demo
if kind get clusters | grep -qx "$cluster"; then
  kind export kubeconfig --name "$cluster" --kubeconfig "$KUBECONFIG"
else
  kind create cluster --name "$cluster" --kubeconfig "$KUBECONFIG"
fi
if [ -n "${KIND_IMAGE_PLATFORM:-}" ]; then
  docker build --platform "$KIND_IMAGE_PLATFORM" -t document-events-outbox:demo .
else
  docker build -t document-events-outbox:demo .
fi
for image in postgres:16-alpine rabbitmq:4-management-alpine; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"
done
set -- document-events-outbox:demo postgres:16-alpine rabbitmq:4-management-alpine
if [ -n "${KIND_IMAGE_PLATFORM:-}" ]; then
  # A platform-specific archive avoids missing OCI manifests in Docker's containerd image store.
  archive=$(mktemp)
  trap 'rm -f "$archive"' EXIT
  docker image save --platform "$KIND_IMAGE_PLATFORM" --output "$archive" "$@"
  kind load image-archive --name "$cluster" "$archive"
  rm -f "$archive"
  trap - EXIT
else
  kind load docker-image --name "$cluster" "$@"
fi
if ! kubectl get secret credentials >/dev/null 2>&1; then
  kubectl create secret generic credentials --from-literal=DEMO_PASSWORD="$(openssl rand -hex 24)"
fi
kubectl apply -k deploy/k8s
kubectl rollout status sts/postgres --timeout=180s
kubectl rollout status sts/rabbitmq --timeout=180s
kubectl delete job/migrate --ignore-not-found
kubectl apply -k deploy/k8s/migrations
kubectl wait --for=condition=complete job/migrate --timeout=300s
kubectl apply -k deploy/k8s/services
kubectl rollout restart deploy/api deploy/relay deploy/consumer
for app in api relay consumer; do kubectl rollout status deployment/"$app" --timeout=180s; done
