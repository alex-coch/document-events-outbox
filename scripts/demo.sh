#!/bin/sh
set -eu
mode=$1
scenario=$2
event_id=
paused_container=
export KUBECONFIG="$PWD/.demo/kubeconfig"
dc() { docker compose "$@"; }
k() { kubectl --request-timeout=12s "$@"; }
probe() {
  if [ "$mode" = k8s ]; then k exec deploy/api -- python -m scripts.probe "$@"
  else dc exec -T api python -m scripts.probe "$@"; fi
}
wait_for() {
  deadline=$(( $(date +%s) + 120 ))
  log_file=$(mktemp)
  until "$@" >"$log_file" 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      cat "$log_file" >&2; rm -f "$log_file"
      echo "Timed out: $*" >&2; return 1
    fi
    sleep 1
  done
  cat "$log_file"; rm -f "$log_file"
}
cleanup() {
  result=$?
  trap - EXIT
  set +e
  if [ "$result" -ne 0 ]; then
    echo "Demo failed: mode=$mode scenario=$scenario event_id=$event_id" >&2
    if [ "$mode" = k8s ]; then
      k get pods; k logs deploy/consumer --tail=30; k logs deploy/relay --tail=30
    else dc ps -a; dc logs --tail=30 consumer relay; fi
  fi
  if [ "$mode" = k8s ]; then
    k scale sts/rabbitmq --replicas=1 >/dev/null
    if [ "$scenario" = redelivery ]; then
      k set env deploy/consumer PAUSE_BEFORE_ACK- >/dev/null
      k scale deploy/consumer --replicas=1 >/dev/null
      kubectl rollout status deploy/consumer --timeout=120s >/dev/null || exit 1
    fi
  else
    if [ -n "$paused_container" ]; then docker rm -f "$paused_container" >/dev/null 2>&1; fi
    dc start rabbitmq consumer >/dev/null || exit 1
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ "$scenario" = outage ]; then
  if [ "$mode" = k8s ]; then
    k scale sts/rabbitmq --replicas=0
    kubectl wait --for=delete pod/rabbitmq-0 --timeout=120s
  else dc stop rabbitmq; fi
  event_id=$(probe create)
  probe pending "$event_id"
  if [ "$mode" = k8s ]; then k scale sts/rabbitmq --replicas=1
  else dc start rabbitmq; fi
  wait_for probe delivered "$event_id"
  exit
fi

if [ "$mode" = k8s ]; then
  k scale deploy/consumer --replicas=0
  kubectl wait --for=delete pod -l app=consumer --timeout=120s
else dc stop consumer; fi
event_id=$(probe create)
if [ "$mode" = k8s ]; then
  k set env deploy/consumer PAUSE_BEFORE_ACK="$event_id"
  k scale deploy/consumer --replicas=1
  kubectl rollout status deploy/consumer --timeout=120s
  pod=$(k get pod -l app=consumer -o jsonpath='{.items[0].metadata.name}')
  old_uid=$(k get pod "$pod" -o jsonpath='{.metadata.uid}')
else
  paused_container=$(dc run -d --no-deps -e PAUSE_BEFORE_ACK="$event_id" consumer)
fi
paused() {
  if [ "$mode" = k8s ]; then k logs "$pod"
  else docker logs "$paused_container"; fi | grep "$event_id" | grep committed_before_ack
}
wait_for paused
wait_for probe delivered "$event_id"
if [ "$mode" = k8s ]; then
  k delete pod "$pod" --force --grace-period=0
  replacement() {
    new_uid=$(k get pods -l app=consumer -o jsonpath='{.items[0].metadata.uid}')
    [ -n "$new_uid" ] && [ "$new_uid" != "$old_uid" ]
  }
  wait_for replacement
  echo "Consumer UID: $old_uid -> $new_uid"
else
  docker kill "$paused_container" >/dev/null
  dc start consumer
fi
redelivered() {
  if [ "$mode" = k8s ]; then k logs deploy/consumer
  else dc logs consumer; fi | grep "$event_id" | grep duplicate_skipped | grep '"redelivered": true'
}
wait_for redelivered
probe delivered "$event_id"
empty_queue() {
  if [ "$mode" = k8s ]; then k exec rabbitmq-0 -- rabbitmqctl -q list_queues name messages_ready messages_unacknowledged
  else dc exec -T rabbitmq rabbitmqctl -q list_queues name messages_ready messages_unacknowledged; fi |
    awk '$1=="document.submitted.v1" && $2=="0" && $3=="0" {print; ok=1} END {exit !ok}'
}
wait_for empty_queue
