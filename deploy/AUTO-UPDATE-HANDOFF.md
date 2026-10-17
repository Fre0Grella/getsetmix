# Auto-update handoff: GetSetMix redeploys itself on every push to `main`

> Handoff for the session that sets this up on the home server. Read it
> top to bottom; it's ordered. Run the checks in "Before you change anything"
> first and stop to ask if the live cluster doesn't match what's described.

## Goal

Every push to `main` should end up running on the home server with no manual
`kubectl rollout restart`, and so should the weekly yt-dlp refresh (an image
more than a few months old starts failing YouTube downloads with HTTP 403; see
issue #9).

## How images are already published (nothing to change here)

- `.github/workflows/docker-publish.yml` runs on every push to `main` **and**
  every Monday (04:17 UTC). Each run resolves the newest yt-dlp and pushes
  `ghcr.io/fre0grella/getsetmix:latest` (also `:main` and `:sha-…`) for
  amd64 + arm64.
- `.github/workflows/release.yml` also pushes immutable semver tags (`:1.3.0`,
  `:1.3`, `:1`) when semantic-release cuts a release. The weekly refresh does
  **not** produce semver tags; it only moves `:latest`.

So the server only needs something that notices the digest behind `:latest`
changing and rolls the deployment.

## The live deployment (differs from the repo manifest)

- Single-node **MicroK8s** on `freoserver`.
- Namespace **`nextcloud`** (the repo's `deploy/k8s/getsetmix.yaml` says
  `getsetmix`; the live one is what counts), Deployment **`getsetmix`**.
- Image `ghcr.io/fre0grella/getsetmix:latest`.
- State is SQLite on a PVC, so only one pod may run at a time.

## Chosen approach: Keel (pull-based, credentials stay in the cluster)

[Keel](https://keel.sh) is one small operator that polls the registry and does
a rolling update when the watched tag's digest changes. `keel.sh/policy: force`
plus `keel.sh/match-tag: "true"` means "stay on `:latest`, roll whenever its
digest changes". Expected latency from push to running: ~6 min image build +
up to the poll interval.

Rejected alternatives, for the record:

- **Push from GitHub Actions** (join the tailnet with `tailscale/github-action`,
  then `kubectl rollout restart`): instant, but puts a cluster kubeconfig in
  GitHub secrets.
- **Argo CD Image Updater / Flux image automation**: right for GitOps, heavy
  for one deployment.
- **A CronJob that restarts nightly**: restarts even when nothing changed and
  lags up to a day.

## Before you change anything

Run these and compare against the expectations. Stop and ask on a mismatch.

```bash
kubectl -n nextcloud get deploy getsetmix -o wide
# container name(s): the patch below assumes "getsetmix"
kubectl -n nextcloud get deploy getsetmix -o jsonpath='{.spec.template.spec.containers[*].name}{"\n"}'
# must be Recreate (or RollingUpdate with maxSurge 0): two pods on one SQLite DB is unsafe
kubectl -n nextcloud get deploy getsetmix -o jsonpath='{.spec.strategy}{"\n"}'
# image + pull policy
kubectl -n nextcloud get deploy getsetmix -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.template.spec.containers[0].imagePullPolicy}{"\n"}'
# private GHCR package? then a pull secret must exist and be referenced here
kubectl -n nextcloud get deploy getsetmix -o jsonpath='{.spec.template.spec.imagePullSecrets}{"\n"}'
microk8s status | grep -i helm   # helm3 addon available?
```

If the strategy is `RollingUpdate` with surge, fix that first (with the user's
OK):

```bash
kubectl -n nextcloud patch deploy getsetmix -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
```

## Step 1: install Keel

```bash
microk8s enable helm3            # if the addon isn't enabled yet
microk8s helm3 repo add keel https://charts.keel.sh
microk8s helm3 repo update
microk8s helm3 upgrade --install keel keel/keel -n keel --create-namespace \
  --set helmProvider.enabled=false
kubectl -n keel rollout status deploy/keel
```

`helmProvider.enabled=false` because GetSetMix is plain manifests, not a Helm
release.

## Step 2: opt the deployment in

```bash
kubectl -n nextcloud annotate deploy/getsetmix --overwrite \
  keel.sh/policy=force \
  keel.sh/match-tag=true \
  keel.sh/trigger=poll \
  keel.sh/pollSchedule="@every 5m"

# Always pull, or a restarted pod may keep the cached old :latest.
kubectl -n nextcloud patch deploy getsetmix -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"getsetmix","imagePullPolicy":"Always"}]}}}}'
```

Adjust the container name in the patch if the check above printed something
other than `getsetmix`.

**Registry access:** if the GHCR package is private, Keel uses the
deployment's `imagePullSecrets` to poll. Make sure a `ghcr.io` docker-registry
secret (a token with `read:packages`) exists in `nextcloud` and is referenced.
Simpler: make the package public (GitHub ▸ Packages ▸ getsetmix ▸ Package
settings ▸ Change visibility).

## Step 3: verify end to end

```bash
kubectl -n keel logs deploy/keel --tail=50 | grep -i getsetmix   # Keel registered the watch
```

Trigger a real update without a code change by re-running the image workflow:

```bash
gh workflow run docker-publish.yml --repo Fre0Grella/getsetmix --ref main
gh run watch --repo Fre0Grella/getsetmix "$(gh run list --repo Fre0Grella/getsetmix --workflow docker-publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Within ~5 minutes of that run finishing:

```bash
kubectl -n nextcloud get pods -l app=getsetmix -w          # old pod terminates, new one starts
kubectl -n nextcloud get pod -l app=getsetmix \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # digest changed
curl -s http://<getsetmix-host>/api/status                # app version + yt-dlp age, js_runtime "deno"
```

`/api/status` should report `"js_runtime": {"name": "deno", …}` and a small
`age_days`: that's the issue #9 fix in place.

## Step 4 (optional): record it in the repo

Mirror the annotations and `imagePullPolicy: Always` into
`deploy/k8s/getsetmix.yaml` (the pull policy is already there) so a fresh
install gets auto-update too, and add a short "Auto-update" note to the README
Kubernetes section. Commit as `docs:`/`chore:`, not `feat:`, so it doesn't
cut a release.

## Rollback and off switch

```bash
# go back one version
kubectl -n nextcloud rollout undo deploy/getsetmix
# stop auto-updating (Keel ignores un-annotated deployments)
kubectl -n nextcloud annotate deploy/getsetmix keel.sh/policy- keel.sh/match-tag- keel.sh/trigger- keel.sh/pollSchedule-
# remove Keel entirely
microk8s helm3 uninstall keel -n keel && kubectl delete ns keel
```

To pin a known-good version while auto-update is off:
`kubectl -n nextcloud set image deploy/getsetmix getsetmix=ghcr.io/fre0grella/getsetmix:1.3.0`.

## Variant: follow releases instead of every push

Point the deployment at a semver tag (e.g. `:1`) and use
`keel.sh/policy=minor` (drop `match-tag`). Updates then only arrive with
semantic-release versions. Trade-off: the weekly yt-dlp refresh only moves
`:latest`, so this variant would let yt-dlp go stale between releases.
