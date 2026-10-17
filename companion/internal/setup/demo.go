package setup

import (
	"net/http"
	"time"

	"github.com/Fre0Grella/getsetmix/companion/internal/serverscript"
)

// Demo mode plays the whole flow with a pretend server and pretend
// installs: nothing is downloaded, written or started.

var demoFacts = map[string]string{
	"docker": `hostname=nas
os=Ubuntu 24.04.1 LTS
arch=x86_64
ips=192.168.1.10 100.101.102.103
listening=22 80
free:/opt=412316860
free:/mnt=1932735283
docker=27.3.1
tailscale_dns=nas.tail1234.ts.net.
`,
	"k8s-adopt": `hostname=homeserver
os=Ubuntu 22.04.5 LTS
arch=x86_64
ips=192.168.1.5
free:/opt=88080384
kubectl=microk8s kubectl
k8s_node=homeserver
k8s_existing=media/getsetmix|getsetmix|ghcr.io/fre0grella/getsetmix:latest|RollingUpdate
k8s_hosts=getsetmix.tail1234.ts.net
tailscale_dns=homeserver.tail1234.ts.net.
`,
	"bare": `hostname=raspberrypi
os=Debian GNU/Linux 12 (bookworm)
arch=aarch64
ips=192.168.1.30
free:/opt=25165824
`,
}

func (w *Wizard) handleDemoConnect(rw http.ResponseWriter, r *http.Request) {
	var req struct{ Variant string }
	_ = readJSON(r, &req)
	body, ok := demoFacts[req.Variant]
	if !ok {
		body = demoFacts["docker"]
	}
	f := serverscript.ParseFacts(body)
	w.mu.Lock()
	w.facts = &f
	w.srvBase = "http://192.168.1.20:47321/s/" + w.code
	w.plan, w.script, w.cancel = nil, "", false
	w.planCh = make(chan struct{})
	w.srvSteps, w.srvState, w.srvURL, w.urlState = nil, "", "", ""
	w.mu.Unlock()
	writeJSON(rw, map[string]bool{"ok": true})
}

func (w *Wizard) demoServer() {
	time.Sleep(800 * time.Millisecond)
	w.mu.Lock()
	w.srvState = "running"
	ids := make([]string, len(w.srvSteps))
	for i, s := range w.srvSteps {
		ids[i] = s.ID
	}
	w.mu.Unlock()
	for _, id := range ids {
		w.mu.Lock()
		w.setStep(&w.srvSteps, id, "running", "", "")
		w.mu.Unlock()
		time.Sleep(900 * time.Millisecond)
		w.mu.Lock()
		w.setStep(&w.srvSteps, id, "ok", "", "")
		w.mu.Unlock()
	}
	w.mu.Lock()
	w.srvState, w.urlState, w.srvPort = "done", "checking", w.plan.Port
	w.mu.Unlock()
	time.Sleep(700 * time.Millisecond)
	w.mu.Lock()
	url := "http://192.168.1.10:8765"
	if w.plan.Tailscale {
		url = "https://" + w.facts.TailscaleDNS
	} else if e := w.facts.ExistingK8s; e != nil && len(e.Hosts) > 0 {
		url = "https://" + e.Hosts[0]
	}
	w.acceptURL(url, 0)
	w.mu.Unlock()
}

func (w *Wizard) demoStep(id string) error {
	switch id {
	case "app", "ffmpeg", "deno":
		for f := 0.0; f < 1; f += 0.08 {
			w.update(id, "running", "", "", f)
			time.Sleep(90 * time.Millisecond)
		}
	default:
		time.Sleep(600 * time.Millisecond)
	}
	return nil
}
