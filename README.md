# getsetmix

A service for music file ingestion directly onto Rekordbox.

## Kubernetes

Manifests live in `deploy/kubernetes/`.

### Prerequisite: Rekordbox Library PVC

The Deployment expects a user-provided PVC named `rekordbox-library` that points at the Rekordbox Library root (this can be the same PVC you also mount into Nextcloud).

If you want a different PVC name, edit `deploy/kubernetes/02-deployment.yaml` (`volumes[].persistentVolumeClaim.claimName`).

### Apply

```sh
kubectl apply -f deploy/kubernetes/00-configmap.yaml
kubectl apply -f deploy/kubernetes/01-state-pvc.yaml
kubectl apply -f deploy/kubernetes/02-deployment.yaml
kubectl apply -f deploy/kubernetes/03-service.yaml
```

### Optional: static token

Edit `deploy/kubernetes/04-auth-secret.example.yaml` and apply it:

```sh
kubectl apply -f deploy/kubernetes/04-auth-secret.example.yaml
```
