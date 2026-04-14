# Kong on k3s

Uses the upstream kong/kong Helm chart in DB-less mode.

## Install
```bash
# Add Kong repo
helm repo add kong https://charts.konghq.com
helm repo update

# Apply ConfigMap first
kubectl apply -f charts/kong/kong-config.yaml

# Install Kong
helm install kong kong/kong \
  --version 2.38.0 \
  -f charts/kong/values-k3s.yaml \
  -n network --create-namespace
```
