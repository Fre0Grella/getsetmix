# Deploy handoff — GetSetMix v1.2.0 (share target + HTTPS)

> Handoff for the session doing the deploy. Read top-to-bottom; it's ordered.

## Context

GetSetMix already runs in Kubernetes (namespace `getsetmix`, Deployment pinned to
`ghcr.io/Fre0Grella/getsetmix:latest`, Service :80 → container :8765). Two things
shipped in **v1.2.0** that this deploy needs to activate:

1. **Share to GetSetMix** — the web UI is now an installable PWA with a Web Share
   Target, so it appears in the Android share sheet of YouTube/SoundCloud. **This
   only works when the instance is reachable over HTTPS**, because browsers refuse
   to install a PWA from an insecure origin. So the real new infra requirement is a
   **TLS Ingress** in front of the existing Service.
2. New immutable image tags exist: `ghcr.io/Fre0Grella/getsetmix:1.2.0` (+ `:1.2`, `:1`).

Manifests live in `deploy/k8s/getsetmix.yaml` (it already contains a commented TLS
Ingress example to adapt). iOS is **not** supported (Safari has no Web Share Target).

## Prerequisites (confirm before starting)

- `kubectl` access to the cluster; `kubectl -n getsetmix get deploy,svc` works.
- An ingress controller installed (e.g. ingress-nginx, Traefik).
- A DNS name you can point at the ingress (e.g. `getsetmix.your.lab`).
- TLS: either **cert-manager** with a ClusterIssuer (preferred), or a pre-created
  TLS secret in the `getsetmix` namespace.
- If the instance is exposed publicly, decide on auth (`GSM_AUTH_TOKEN` or Basic
  Auth) — see "Auth" below.

## Step 1 — Roll to the versioned image

Pin the immutable tag instead of `:latest` (cleaner for rollback):

```bash
kubectl -n getsetmix set image deployment/getsetmix \
  getsetmix=ghcr.io/Fre0Grella/getsetmix:1.2.0
kubectl -n getsetmix rollout status deployment/getsetmix
```

(If you prefer staying on `:latest`, instead run
`kubectl -n getsetmix rollout restart deployment/getsetmix` — it re-pulls `:latest`.)

## Step 2 — Put it behind HTTPS (the actual new requirement)

Edit `deploy/k8s/getsetmix.yaml`: uncomment the Ingress block at the bottom and set
your host + TLS. It looks like this (cert-manager variant):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: getsetmix
  namespace: getsetmix
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod   # your issuer name
spec:
  tls:
    - hosts: [getsetmix.your.lab]
      secretName: getsetmix-tls                         # cert-manager fills this
  rules:
    - host: getsetmix.your.lab
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: getsetmix
                port: { number: 80 }
```

If NOT using cert-manager, create the TLS secret yourself first and keep the `tls:`
block pointing at it:

```bash
kubectl -n getsetmix create secret tls getsetmix-tls \
  --cert=fullchain.pem --key=privkey.pem
```

Apply, then point DNS `getsetmix.your.lab` at the ingress controller's external IP:

```bash
kubectl apply -f deploy/k8s/getsetmix.yaml
kubectl -n getsetmix get ingress
```

## Step 3 — Verify HTTPS + the PWA endpoints

```bash
curl -fsS https://getsetmix.your.lab/healthz                 # -> ok
curl -fsS https://getsetmix.your.lab/manifest.webmanifest    # -> JSON with "share_target"
curl -fsSI https://getsetmix.your.lab/sw.js | grep -i content-type   # javascript
```

A valid TLS cert (not self-signed) is required — Android Chrome won't offer
"Install" on an untrusted cert.

## Step 4 — Install on Android and test the share

1. Android **Chrome/Edge** → open `https://getsetmix.your.lab` → menu → **Install app /
   Add to Home screen**.
2. Open YouTube or SoundCloud app → a track → **Share** → **GetSetMix**.
3. The PWA opens, the link is fetched, and the track appears staged (highlighted
   row). Edit metadata and hit **Download** — same flow as paste.

## Auth (if exposed beyond the LAN)

- Set `GSM_AUTH_TOKEN` (or `GSM_BASIC_USER`/`GSM_BASIC_PASS`). In k8s:
  `kubectl -n getsetmix create secret generic getsetmix-auth --from-literal=GSM_AUTH_TOKEN=...`
  and uncomment the `secretRef` in the Deployment's `envFrom`.
- With token auth, **open the installed PWA once and enter the token** before
  sharing — it's stored in the browser and reused on share. Basic Auth is handled
  by the browser automatically.

## Verify success / rollback

- Success: `kubectl -n getsetmix get pods` shows the new pod Ready on image
  `:1.2.0`; the three `curl` checks pass; a shared link from the phone lands in the
  UI staged.
- Rollback: `kubectl -n getsetmix rollout undo deployment/getsetmix`
  (or `set image ... :1.1.1`). Removing the Ingress reverts to the prior reachability.

## Gotchas

- **HTTP won't work** for the share feature — must be HTTPS with a trusted cert.
- **iOS is unsupported** (no Web Share Target); paste-link still works there.
- State is SQLite on a PVC: `replicas: 1` + `strategy: Recreate` — don't scale up.
