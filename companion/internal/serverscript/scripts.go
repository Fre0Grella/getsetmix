package serverscript

// The templates use [[ ]] so the {{ }} of docker --format and kubectl
// jsonpath stay readable. Every value that comes from a person or the
// network goes through q (shell quoting) or has passed Plan.Validate.

const bootstrapSh = `#!/bin/sh
# GetSetMix server setup.
#
# You ran this with the command GetSetMix Setup showed on your computer. It
# looks at what this server has, sends that to Setup, waits while you make
# your choices there, then runs the installation Setup sends back.
BASE=[[q .Base]]
say() { printf '%s\n' "$*"; }

if [ "$(id -u)" != 0 ]; then
  say "GetSetMix setup needs administrator rights. Run it like this:"
  say "  curl -fsSL $BASE | sudo sh"
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  say "This setup needs curl. Install it (Debian/Ubuntu: apt install curl) and run the command again."
  exit 1
fi

post() { curl -fsS -m 30 -X POST --data-binary @- "$BASE/$1" >/dev/null; }
kv() { printf '%s=%s\n' "$1" "$2"; }

facts() {
  kv hostname "$(hostname 2>/dev/null)"
  kv os "$( (. /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME") || uname -sr)"
  kv arch "$(uname -m)"
  kv ips "$(hostname -I 2>/dev/null || ip -4 -o addr show scope global 2>/dev/null | awk '{sub("/.*", "", $4); print $4}' | tr '\n' ' ')"
  kv listening "$( (ss -ltnH 2>/dev/null || netstat -ltn 2>/dev/null) | awk '{print $4}' | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | sort -un | tr '\n' ' ')"
  for d in /opt /srv /home /mnt /media; do
    [ -d "$d" ] && kv "free:$d" "$(df -Pk "$d" 2>/dev/null | awk 'NR==2 {print $4}')"
  done

  if command -v docker >/dev/null 2>&1; then
    kv docker "$(docker version --format '{{.Server.Version}}' 2>/dev/null)"
    e=$(docker ps -a --format '{{.Names}}|{{.Image}}' 2>/dev/null | grep -i '|.*getsetmix' | head -n 1)
    if [ -n "$e" ]; then
      p=$(docker port "${e%%|*}" 8765/tcp 2>/dev/null | head -n 1 | sed 's/.*://')
      kv docker_existing "$e|$p"
    fi
  fi

  for k in kubectl "microk8s kubectl" "k3s kubectl"; do
    set -- $k
    command -v "$1" >/dev/null 2>&1 || continue
    $k get nodes -o name >/dev/null 2>&1 || continue
    kv kubectl "$k"
    me=$(hostname | tr 'A-Z' 'a-z')
    node=$($k get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep -ix "$me" | head -n 1)
    [ -n "$node" ] || node=$($k get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    kv k8s_node "$node"
    if $k get deploy -A -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep -qx keel; then
      kv keel 1
    fi
    kv nodeports "$($k get svc -A -o jsonpath='{.items[*].spec.ports[*].nodePort}' 2>/dev/null)"
    e=$($k get deploy -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}|{.spec.template.spec.containers[0].name}|{.spec.template.spec.containers[0].image}|{.spec.strategy.type}{"\n"}{end}' 2>/dev/null | grep -i '|[^|]*getsetmix[^|]*|' | head -n 1)
    if [ -n "$e" ]; then
      kv k8s_existing "$e"
      ns=${e%%/*}
      dep=${e%%|*}
      dep=${dep#*/}
      # Only GetSetMix's own Services and Ingresses: its namespace may hold
      # other apps (Nextcloud next door), whose ports and names aren't ours.
      svcs=$($k -n "$ns" get svc -o jsonpath='{range .items[*]}{.metadata.name}|{.spec.ports[*].nodePort}|{.status.loadBalancer.ingress[*].hostname}{"\n"}{end}' 2>/dev/null | grep -i -e '^[^|]*getsetmix[^|]*|' -e "^$dep|")
      kv k8s_existing_nodeports "$(printf '%s\n' "$svcs" | cut -d'|' -f2 | tr '\n' ' ')"
      hosts=$(printf '%s\n' "$svcs" | cut -d'|' -f3 | tr '\n' ' ')
      ing=$($k -n "$ns" get ingress -o jsonpath='{range .items[*]}{.spec.rules[*].http.paths[*].backend.service.name}|{.spec.rules[*].host} {.status.loadBalancer.ingress[*].hostname}{"\n"}{end}' 2>/dev/null)
      for svc in $(printf '%s\n' "$svcs" | cut -d'|' -f1); do
        hosts="$hosts $(printf '%s\n' "$ing" | grep -E "(^| )$svc( |\|)" | cut -d'|' -f2 | tr '\n' ' ')"
      done
      kv k8s_hosts "$hosts"
    fi
    break
  done

  if command -v tailscale >/dev/null 2>&1; then
    st=$(tailscale status --json 2>/dev/null)
    case "$st" in
      *'"BackendState": "Running"'*)
        kv tailscale_dns "$(printf '%s\n' "$st" | sed -n 's/^ *"DNSName": *"\([^"]*\)".*/\1/p' | head -n 1)"
        case "$(tailscale serve status --json 2>/dev/null)" in
          *':443"'*|*'"443"'*) kv tailscale_https 1 ;;
        esac
        ;;
    esac
  fi
}

say "GetSetMix setup: looking at this server..."
if ! facts | post facts; then
  say "Couldn't reach GetSetMix Setup at $BASE."
  say "Is Setup still open on your computer, and is this server on the same network?"
  exit 1
fi
say ""
say "Now go back to GetSetMix Setup on your computer and finish there."
say "Waiting for your choices..."

plan=$(mktemp 2>/dev/null || echo /tmp/getsetmix-plan.$$)
while :; do
  code=$(curl -sS -m 90 -o "$plan" -w '%{http_code}' "$BASE/plan") || code=000
  case "$code" in
    200) break ;;
    204) continue ;;
    410) say "Setup was cancelled on your computer. Nothing was changed."; rm -f "$plan"; exit 0 ;;
    *) say "Lost the connection to GetSetMix Setup (HTTP $code). Run the command again from Setup."; rm -f "$plan"; exit 1 ;;
  esac
done
sh "$plan"
rc=$?
rm -f "$plan"
exit $rc
`

const planSh = `#!/bin/sh
# GetSetMix installation for [[.Facts.Hostname]], written by GetSetMix Setup.
# Steps: [[.Steps]]
BASE=[[q .Base]]
LOG=/var/log/getsetmix-setup.log
{ : >"$LOG"; } 2>/dev/null || LOG=/tmp/getsetmix-setup.log
CUR=start

post() { curl -fsS -m 30 -X POST --data-binary @- "$BASE/$1" >/dev/null 2>&1 || true; }
step() { CUR=$1; printf '\n==> %s\n' "$2"; printf 'step %s\n' "$1" | post log; }
ok() { printf 'ok %s\n' "$CUR" | post log; }
fail() {
  printf '!! %s failed (%s). Details: %s\n' "$CUR" "$1" "$LOG"
  { printf 'fail %s %s\n' "$CUR" "$1"; tail -n 40 "$LOG"; } | post log
  exit 1
}
warn() { { printf 'warn %s %s\n' "$CUR" "$1"; tail -n 20 "$LOG"; } | post log; }
run() { printf '+ %s\n' "$*" >>"$LOG"; "$@" >>"$LOG" 2>&1; }
[[- if eq .Target "kubernetes"]]
K="[[.Kubectl]]"
[[- end]]

[[- if .InstallDocker]]

step docker "Installing Docker"
run sh -c 'curl -fsSL https://get.docker.com | sh' || fail docker_install
run systemctl enable --now docker
ok
[[- end]]

[[- if eq .Target "docker"]]
[[- if .Adopt]]
[[- if .AutoUpdate]]

step updates "Turning on automatic updates (Watchtower)"
run docker rm -f getsetmix-watchtower
run docker run -d --name getsetmix-watchtower --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  [[.Watchtower]] --cleanup --interval 3600 [[q .Container]] || fail watchtower
ok
[[- end]]

step app "Updating GetSetMix to the newest version"
run docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  [[.Watchtower]] --run-once --cleanup [[q .Container]] || warn update
run docker start [[q .Container]]
ok
PORT=$(docker port [[q .Container]] 8765/tcp 2>/dev/null | head -n 1 | sed 's/.*://')
[ -n "$PORT" ] || { CUR=start; fail no_port; }
[[- else]]

step folders "Creating the folders"
run mkdir -p [[q .DataDir]] [[q .MusicDir]] || fail folders
ok

step app "Installing GetSetMix"
[[- if .Pull]]
run docker pull [[q .Image]] || fail pull
[[- end]]
run docker rm -f [[q .Container]]
run docker run -d --name [[q .Container]] --restart unless-stopped \
  -p [[.Port]]:8765 \
  -v [[q .DataDir]]:/data -v [[q .MusicDir]]:/music \
  -e GSM_LANGUAGE=[[q .Language]] \
  --label com.centurylinklabs.watchtower.scope=[[.Scope]] \
  [[q .Image]] || fail run
ok
[[- if .AutoUpdate]]

step updates "Turning on automatic updates (Watchtower)"
run docker rm -f getsetmix-watchtower
run docker run -d --name getsetmix-watchtower --restart unless-stopped \
  --label com.centurylinklabs.watchtower.scope=[[.Scope]] \
  -v /var/run/docker.sock:/var/run/docker.sock \
  [[.Watchtower]] --scope [[.Scope]] --cleanup --interval 3600 || fail watchtower
ok
[[- end]]
PORT=[[.Port]]
[[- end]]

step start "Waiting for GetSetMix to start"
i=0
until docker exec [[q .Container]] python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3)" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -ge 90 ] && { docker logs --tail 40 [[q .Container]] >>"$LOG" 2>&1; fail health; }
  sleep 2
done
ok

step link "Connecting your computer"
docker exec [[q .Container]] sh -c 'umask 077; printf "%s  %s\n" "$1" "$2" >> "${GSM_DATA_DIR:-/data}/link-tokens"' \
  sh [[q .Token]] [[q (label .Label)]] >>"$LOG" 2>&1 || fail link
ok
[[- else]]
[[- if .Adopt]]

step updates "Turning on automatic updates (Keel)"
[[- if ne .Facts.ExistingK8s.Strategy "Recreate"]]
# One copy at a time: two would share one SQLite database.
run $K -n [[q .Namespace]] patch deploy [[q .Name]] --type merge \
  -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}' || fail patch
[[- end]]
# Pull on every start, or a restart could keep a cached old :latest.
run $K -n [[q .Namespace]] patch deploy [[q .Name]] \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"[[json .Facts.ExistingK8s.Container]]","imagePullPolicy":"Always"}]}}}}' || fail patch
[[- if .AutoUpdate]]
run $K -n [[q .Namespace]] annotate deploy [[q .Name]] --overwrite \
  keel.sh/policy=force keel.sh/match-tag=true keel.sh/trigger=poll 'keel.sh/pollSchedule=@every 5m' || fail patch
[[- if not .Facts.Keel]]
$K apply -f - >>"$LOG" 2>&1 <<'KEEL' || fail keel
[[keel]]
KEEL
[[- end]]
[[- end]]
ok

step app "Updating GetSetMix to the newest version"
run $K -n [[q .Namespace]] rollout restart deploy [[q .Name]] || fail restart
ok
[[- else]]

step folders "Creating the folders"
run mkdir -p [[q .DataDir]] [[q .MusicDir]] || fail folders
ok

step app "Installing GetSetMix"
$K apply -f - >>"$LOG" 2>&1 <<'MANIFEST' || fail apply
apiVersion: v1
kind: Namespace
metadata:
  name: [[.Namespace]]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: [[.Name]]
  namespace: [[.Namespace]]
  labels:
    app: getsetmix
[[- if .AutoUpdate]]
  annotations:
    keel.sh/policy: force
    keel.sh/match-tag: "true"
    keel.sh/trigger: poll
    keel.sh/pollSchedule: "@every 5m"
[[- end]]
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: getsetmix
  template:
    metadata:
      labels:
        app: getsetmix
    spec:
[[- if .Facts.K8sNode]]
      nodeSelector:
        kubernetes.io/hostname: "[[json .Facts.K8sNode]]"
[[- end]]
      containers:
        - name: getsetmix
          image: "[[json .Image]]"
          imagePullPolicy: [[if .Pull]]Always[[else]]IfNotPresent[[end]]
          ports:
            - containerPort: 8765
          env:
            - name: GSM_LANGUAGE
              value: "[[json .Language]]"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8765
          volumeMounts:
            - name: data
              mountPath: /data
            - name: music
              mountPath: /music
      volumes:
        - name: data
          hostPath:
            path: "[[json .DataDir]]"
            type: DirectoryOrCreate
        - name: music
          hostPath:
            path: "[[json .MusicDir]]"
            type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: [[.Name]]
  namespace: [[.Namespace]]
spec:
  type: NodePort
  selector:
    app: getsetmix
  ports:
    - port: 80
      targetPort: 8765
      nodePort: [[.Port]]
MANIFEST
ok
[[- if .AutoUpdate]]

step updates "Turning on automatic updates (Keel)"
[[- if not .Facts.Keel]]
$K apply -f - >>"$LOG" 2>&1 <<'KEEL' || fail keel
[[keel]]
KEEL
[[- end]]
ok
[[- end]]
[[- end]]

step start "Waiting for GetSetMix to start"
run $K -n [[q .Namespace]] rollout status deploy [[q .Name]] --timeout=600s || {
  $K -n [[q .Namespace]] describe pods -l app=getsetmix >>"$LOG" 2>&1
  fail health
}
ok

step link "Connecting your computer"
$K -n [[q .Namespace]] exec deploy/[[.Name]] -- sh -c 'umask 077; printf "%s  %s\n" "$1" "$2" >> "${GSM_DATA_DIR:-/data}/link-tokens"' \
  sh [[q .Token]] [[q (label .Label)]] >>"$LOG" 2>&1 || fail link
ok
PORT=[[.Port]]
[[- end]]

[[- if .Tailscale]]

step https "Turning on HTTPS with Tailscale"
T=""
command -v timeout >/dev/null 2>&1 && T="timeout 40"
if $T tailscale serve --bg --https=[[.TailscalePort]] "http://127.0.0.1:$PORT" >>"$LOG" 2>&1; then
  ok
else
  warn tailscale
fi
[[- end]]

printf 'done %s\n' "$PORT" | post log
printf '\nAll done. Go back to GetSetMix Setup on your computer.\n'
`
