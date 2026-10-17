package serverscript

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const base = "http://192.168.1.20:47321/s/ABCD2345"

const dockerFacts = `hostname=nas
os=Ubuntu 24.04.1 LTS
arch=x86_64
ips=192.168.1.10 100.101.102.103 fd7a:115c::1
listening=22 80 8765
free:/opt=52428800
docker=27.3.1
tailscale_dns=nas.tail1234.ts.net.
tailscale_https=1
`

const k8sAdoptFacts = `hostname=freoserver
ips=192.168.1.5
kubectl=microk8s kubectl
k8s_node=freoserver
nodeports=30080 30765
k8s_existing=nextcloud/getsetmix|getsetmix|ghcr.io/fre0grella/getsetmix:latest|RollingUpdate
k8s_hosts=getsetmix-freoserver-1.elephant-elver.ts.net  getsetmix-freoserver-1.elephant-elver.ts.net
k8s_existing_nodeports=
`

func TestParseFacts(t *testing.T) {
	f := ParseFacts(dockerFacts)
	if f.Hostname != "nas" || f.Docker != "27.3.1" || len(f.IPs) != 2 || f.TailscaleDNS != "nas.tail1234.ts.net" ||
		!f.TailscaleHTTPSIn || !f.Listening[8765] || f.FreeKB["/opt"] != 52428800 {
		t.Fatalf("%+v", f)
	}
	k := ParseFacts(k8sAdoptFacts)
	e := k.ExistingK8s
	if e == nil || e.Namespace != "nextcloud" || e.Name != "getsetmix" || e.Strategy != "RollingUpdate" ||
		len(e.Hosts) != 1 || k.Kubectl != "microk8s kubectl" || !k.NodePorts[30765] {
		t.Fatalf("%+v %+v", k, e)
	}
}

func TestDefaults(t *testing.T) {
	p := Plan{Facts: ParseFacts(dockerFacts), Token: strings.Repeat("a", 32)}
	p.Defaults()
	if p.Target != "docker" || p.Port != 8766 || p.TailscalePort != 8443 || !p.Pull || p.InstallDocker {
		t.Fatalf("%+v", p)
	}
	p = Plan{Facts: ParseFacts("hostname=bare\n")}
	p.Defaults()
	if p.Target != "docker" || !p.InstallDocker || p.Port != 8765 || p.TailscalePort != 443 {
		t.Fatalf("%+v", p)
	}
	p = Plan{Facts: ParseFacts(k8sAdoptFacts), Adopt: true}
	p.Defaults()
	if p.Target != "kubernetes" || p.Port != 0 {
		t.Fatalf("%+v", p)
	}
	p = Plan{Facts: ParseFacts("kubectl=k3s kubectl\nnodeports=30765\n")}
	p.Defaults()
	if p.Target != "kubernetes" || p.Port != 30766 {
		t.Fatalf("%+v", p)
	}
}

func plans() map[string]Plan {
	tok := "Zk3_9aQ-0123456789abcdefABCDEF"
	mk := func(facts string, mod func(*Plan)) Plan {
		p := Plan{Facts: ParseFacts(facts), Token: tok, Label: "Marco's PC; rm -rf /", AutoUpdate: true}
		if mod != nil {
			mod(&p)
		}
		p.Defaults()
		return p
	}
	return map[string]Plan{
		"docker":         mk(dockerFacts, func(p *Plan) { p.Tailscale = true; p.MusicDir = "/mnt/big disk/music" }),
		"docker-install": mk("hostname=bare\n", func(p *Plan) { p.AutoUpdate = false }),
		"docker-adopt": mk(dockerFacts+"docker_existing=gsm|ghcr.io/fre0grella/getsetmix:1.4.0|8765\n",
			func(p *Plan) { p.Adopt = true; p.Tailscale = true }),
		"docker-local-image": mk(dockerFacts, func(p *Plan) { p.Image = "getsetmix:dev" }),
		"k8s":                mk("hostname=k\nkubectl=kubectl\nk8s_node=k\n", func(p *Plan) { p.Language = "it" }),
		"k8s-keel-present":   mk("hostname=k\nkubectl=k3s kubectl\nkeel=1\n", nil),
		"k8s-adopt":          mk(k8sAdoptFacts, func(p *Plan) { p.Adopt = true }),
		"k8s-adopt-noupdate": mk(k8sAdoptFacts, func(p *Plan) { p.Adopt = true; p.AutoUpdate = false }),
	}
}

func TestScriptsAreValidShell(t *testing.T) {
	sh, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("no sh")
	}
	dir := t.TempDir()
	check := func(name, script string) {
		path := filepath.Join(dir, name+".sh")
		if err := os.WriteFile(path, []byte(script), 0o644); err != nil {
			t.Fatal(err)
		}
		if out, err := exec.Command(sh, "-n", path).CombinedOutput(); err != nil {
			t.Errorf("%s: %v\n%s", name, err, out)
		}
	}
	check("bootstrap", Bootstrap(base))
	for name, p := range plans() {
		s, err := Script(base, p)
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		check(name, s)
		if strings.Contains(s, "[[") || strings.Contains(s, "<no value>") {
			t.Errorf("%s: template residue", name)
		}
	}
}

func TestScriptContents(t *testing.T) {
	ps := plans()
	get := func(name string) string {
		s, err := Script(base, ps[name])
		if err != nil {
			t.Fatal(err)
		}
		return s
	}
	must := func(name, s string, want ...string) {
		for _, w := range want {
			if !strings.Contains(s, w) {
				t.Errorf("%s: missing %q", name, w)
			}
		}
	}
	mustNot := func(name, s string, bad ...string) {
		for _, b := range bad {
			if strings.Contains(s, b) {
				t.Errorf("%s: unexpected %q", name, b)
			}
		}
	}
	d := get("docker")
	must("docker", d, "-p 8766:8765", "'/mnt/big disk/music':/music", "docker pull 'ghcr.io/fre0grella/getsetmix:latest'",
		WatchtowerImage+" --scope getsetmix", "tailscale serve --bg --https=8443",
		// the label is cleaned, then quoted: no way out of the string
		"'Marcos PC rm -rf'")
	mustNot("docker", d, "get.docker.com", "Marco's")

	must("docker-install", get("docker-install"), "get.docker.com")
	mustNot("docker-install", get("docker-install"), WatchtowerImage)

	da := get("docker-adopt")
	must("docker-adopt", da, "--run-once --cleanup 'gsm'", "--interval 3600 'gsm'", "docker port 'gsm' 8765/tcp")
	mustNot("docker-adopt", da, "docker rm -f 'gsm'", "mkdir -p")

	mustNot("docker-local-image", get("docker-local-image"), "docker pull")

	k := get("k8s")
	must("k8s", k, `K="kubectl"`, "keel.sh/policy: force", "type: Recreate", "nodePort: 30765",
		`kubernetes.io/hostname: "k"`, "image: keelhq/keel:0.20.0", `value: "it"`, "imagePullPolicy: Always")
	mustNot("k8s-keel-present", get("k8s-keel-present"), "keelhq/keel")

	ka := get("k8s-adopt")
	must("k8s-adopt", ka, `K="microk8s kubectl"`, "-n 'nextcloud' patch deploy 'getsetmix' --type merge",
		`"name":"getsetmix","imagePullPolicy":"Always"`, "keel.sh/policy=force", "rollout restart deploy 'getsetmix'",
		"exec deploy/getsetmix")
	mustNot("k8s-adopt", ka, "kind: Namespace\nmetadata:\n  name: getsetmix", "mkdir -p")
	kn := get("k8s-adopt-noupdate")
	must("k8s-adopt-noupdate", kn, `"imagePullPolicy":"Always"`, "rollout restart")
	mustNot("k8s-adopt-noupdate", kn, "keel.sh/policy")
}

func TestValidateRefusesInjection(t *testing.T) {
	ok := plans()["docker"]
	for name, mod := range map[string]func(*Plan){
		"token":    func(p *Plan) { p.Token = "abc'; reboot; '" },
		"music":    func(p *Plan) { p.MusicDir = "/srv/$(reboot)" },
		"relative": func(p *Plan) { p.DataDir = "data" },
		"dotdot":   func(p *Plan) { p.DataDir = "/srv/../etc" },
		"image":    func(p *Plan) { p.Image = "x; reboot" },
		"kubectl":  func(p *Plan) { p.Target = "kubernetes"; p.Facts.Kubectl = "kubectl; reboot" },
		"language": func(p *Plan) { p.Language = "xx" },
		"adopt":    func(p *Plan) { p.Adopt = true },
	} {
		p := ok
		p.Facts.ExistingDocker = nil
		mod(&p)
		if _, err := Script(base, p); err == nil {
			t.Errorf("%s accepted", name)
		}
	}
}

// TestBootstrapScopesExistingK8s runs the real bootstrap against a fake
// kubectl whose GetSetMix shares its namespace with Nextcloud (as on a
// homelab that put it there): only GetSetMix's own port and host names may
// come back, or Setup would offer to serve Nextcloud over Tailscale.
func TestBootstrapScopesExistingK8s(t *testing.T) {
	sh, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("no sh")
	}
	dir := t.TempDir()
	bin := filepath.Join(dir, "bin")
	os.Mkdir(bin, 0o755)
	fake := map[string]string{
		"id":        "echo 0",
		"docker":    "exit 1",
		"tailscale": "exit 1",
		"curl": `for a in "$@"; do last=$a; done
case "$*" in
  *"-X POST"*) cat > "$OUT/$(basename "$last")" ;;
  *"-w"*) echo 410 ;;
esac`,
		"kubectl": `case "$*" in
  "get nodes -o name") echo node/srv ;;
  "get nodes -o jsonpath="*) echo srv ;;
  "get deploy -A -o jsonpath="*"containers[0].image"*)
    printf 'nextcloud/nextcloud|nextcloud|nextcloud:29|Recreate\nnextcloud/getsetmix|getsetmix|ghcr.io/fre0grella/getsetmix:latest|RollingUpdate\n' ;;
  "get deploy -A -o jsonpath="*) printf 'nextcloud\ngetsetmix\n' ;;
  "get svc -A"*) echo "30080 30765 30081" ;;
  "-n nextcloud get svc"*)
    printf 'nextcloud|30080|\ngetsetmix|30765|\nnextcloud-ts|30081|nextcloud.tail.ts.net\n' ;;
  "-n nextcloud get ingress"*"defaultBackend"*)
    printf 'nextcloud |cloud.example.com nextcloud.tail.ts.net\n getsetmix|  getsetmix-srv.tail.ts.net\n' ;;
  *) exit 1 ;;
esac`,
	}
	for name, body := range fake {
		os.WriteFile(filepath.Join(bin, name), []byte("#!/bin/sh\n"+body+"\n"), 0o755)
	}
	script := filepath.Join(dir, "bootstrap.sh")
	os.WriteFile(script, []byte(Bootstrap("http://setup.test/s/abc")), 0o644)
	cmd := exec.Command(sh, script)
	cmd.Env = append(os.Environ(), "OUT="+dir, "PATH="+bin+string(os.PathListSeparator)+"/usr/bin"+string(os.PathListSeparator)+"/bin")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("bootstrap: %v\n%s", err, out)
	}
	body, err := os.ReadFile(filepath.Join(dir, "facts"))
	if err != nil {
		t.Fatal(err)
	}
	f := ParseFacts(string(body))
	e := f.ExistingK8s
	if e == nil || e.Namespace != "nextcloud" || e.Name != "getsetmix" || f.Kubectl != "kubectl" {
		t.Fatalf("existing %+v\n%s", e, body)
	}
	if len(e.NodePorts) != 1 || e.NodePorts[0] != 30765 {
		t.Errorf("node ports %v: only GetSetMix's", e.NodePorts)
	}
	if strings.Join(e.Hosts, " ") != "getsetmix-srv.tail.ts.net" {
		t.Errorf("hosts %q: only GetSetMix's", e.Hosts)
	}
}
