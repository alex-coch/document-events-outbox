.PHONY: up down test demo-broker-outage demo-redelivery k8s-up k8s-down k8s-test k8s-demo-broker-outage k8s-demo-redelivery
up:
	docker compose up --build -d --wait

down:
	docker compose down

test:
	docker compose exec -T api python -m pytest -q -p no:cacheprovider

demo-broker-outage:
	sh scripts/demo.sh compose outage

demo-redelivery:
	sh scripts/demo.sh compose redelivery

k8s-up:
	sh scripts/k8s-up.sh

k8s-down:
	kind delete cluster --name outbox-demo

k8s-test:
	KUBECONFIG=$(CURDIR)/.demo/kubeconfig kubectl exec deploy/api -- python -m pytest -q -p no:cacheprovider

k8s-demo-broker-outage:
	sh scripts/demo.sh k8s outage

k8s-demo-redelivery:
	sh scripts/demo.sh k8s redelivery
