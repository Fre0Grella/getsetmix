# getsetmix

A service for music file ingestion directly onto Rekordbox.

## Developer workflow

This project uses `just` as a lightweight task runner. Install it from https://github.com/casey/just.

Common commands:

```sh
just adapter-deps
just adapter-dev-deps
just format
just lint
just test
just build
just run
just adapter-run
```

### Git pre-commit hook (manual)

This repo uses a simple git hook that runs `just format`, stages formatting changes, then runs `just lint` and `just test`.

```sh
git config core.hooksPath .githooks
```

## Container images

CI/CD publishes images to GitHub Container Registry:

- `ghcr.io/fre0grella/getsetmix`
- `ghcr.io/fre0grella/getsetmix-adapter-runtime`

Tags include `latest` and the git SHA (used for pinning in Kubernetes).

## Kubernetes

Manifests live in `deploy/kubernetes/`.

### MicroK8s quickstart (self-hosted)

On your server with MicroK8s:

```sh
git clone https://github.com/Fre0Grella/getsetmix.git
cd getsetmix

# Edit environment values before applying.
microk8s kubectl apply -f deploy/kubernetes/00-configmap.yaml

microk8s kubectl apply -f deploy/kubernetes/01-state-pvc.yaml
microk8s kubectl apply -f deploy/kubernetes/02-deployment.yaml
microk8s kubectl apply -f deploy/kubernetes/03-service.yaml
microk8s kubectl apply -f deploy/kubernetes/05-nats.yaml
```

Check status:

```sh
microk8s kubectl get pods
microk8s kubectl get svc
```

The Service is `ClusterIP`. Expose it with an Ingress or run:

```sh
microk8s kubectl port-forward svc/getsetmix 8000:8000
```

### Prerequisite: Rekordbox Library PVC

The Deployment expects a user-provided PVC named `rekordbox-library` that points at the Rekordbox Library root (this can be the same PVC you also mount into Nextcloud).

If you want a different PVC name, edit `deploy/kubernetes/02-deployment.yaml` (`volumes[].persistentVolumeClaim.claimName`).

### Configure environment variables

Environment variables live in `deploy/kubernetes/00-configmap.yaml` under `data:`. Update those values before applying, or edit the live ConfigMap:

```sh
microk8s kubectl edit configmap getsetmix-config
microk8s kubectl rollout restart deployment/getsetmix
```

Key fields you will likely change:

- `GSM_REKORDBOX_XML_PATH`
- `GSM_OUTPUT_SUBDIR`
- `GSM_INBOX_PLAYLIST`
- `GSM_OUTPUT_FORMAT`

### Apply

```sh
kubectl apply -f deploy/kubernetes/00-configmap.yaml
kubectl apply -f deploy/kubernetes/01-state-pvc.yaml
kubectl apply -f deploy/kubernetes/02-deployment.yaml
kubectl apply -f deploy/kubernetes/03-service.yaml
kubectl apply -f deploy/kubernetes/05-nats.yaml
```

### Optional: static token

Edit `deploy/kubernetes/04-auth-secret.example.yaml` and apply it:

```sh
kubectl apply -f deploy/kubernetes/04-auth-secret.example.yaml
```
