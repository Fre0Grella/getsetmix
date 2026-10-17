// Package serverscript writes the shell scripts that set up GetSetMix on a
// home server for the setup wizard.
//
// The user pastes one line on the server:
//
//	curl -fsSL http://<this computer>:<port>/s/<code> | sudo sh
//
// That fetches Bootstrap, which reports what the server has (Facts) back to
// the wizard and waits. When the user has made their choices, the wizard
// answers with Script(Plan): plain shell that installs or adopts GetSetMix,
// turns on automatic updates, pairs this computer and reports each step.
// Everything that decides anything lives here in Go, where it is tested; the
// shell only runs commands, so a curious user can read exactly what runs.
package serverscript

import (
	"bytes"
	_ "embed"
	"fmt"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"text/template"
)

// Images. Watchtower is the maintained fork (containrrr/watchtower is
// archived); Keel is pinned in keel.yaml.
const (
	DefaultImage     = "ghcr.io/fre0grella/getsetmix:latest"
	WatchtowerImage  = "nickfedor/watchtower:1.23"
	WatchtowerScope  = "getsetmix"
	DefaultDataDir   = "/opt/getsetmix/data"
	DefaultMusicDir  = "/opt/getsetmix/music"
	DefaultPort      = 8765
	DefaultNodePort  = 30765
	containerName    = "getsetmix"
	watchtowerName   = "getsetmix-watchtower"
	defaultNamespace = "getsetmix"
)

//go:embed keel.yaml
var keelManifest string

// Facts is what the bootstrap found on the server.
type Facts struct {
	Hostname string
	OS       string
	Arch     string
	IPs      []string

	Docker  string // server version; empty when Docker is missing or stopped
	Kubectl string // the kubectl that reaches a cluster ("microk8s kubectl"…)
	K8sNode string // the node this server is
	Keel    bool   // Keel already runs in the cluster

	ExistingDocker *ExistingDocker
	ExistingK8s    *ExistingK8s

	TailscaleDNS     string // this server's MagicDNS name, when Tailscale is up
	TailscaleHTTPSIn bool   // something already serves HTTPS on :443 through Tailscale

	Listening map[int]bool // TCP ports in use
	NodePorts map[int]bool // NodePorts in use in the cluster
	FreeKB    map[string]int64
}

// ExistingDocker is a GetSetMix container already on the server.
type ExistingDocker struct {
	Name, Image string
	Port        int // host port published for 8765; 0 if none
}

// ExistingK8s is a GetSetMix deployment already in the cluster.
type ExistingK8s struct {
	Namespace, Name, Container, Image, Strategy string
	Hosts                                       []string // ingress / load balancer host names
	NodePorts                                   []int
}

// ParseFacts reads the bootstrap's key=value report.
func ParseFacts(body string) Facts {
	f := Facts{Listening: map[int]bool{}, NodePorts: map[int]bool{}, FreeKB: map[string]int64{}}
	for _, line := range strings.Split(body, "\n") {
		k, v, ok := strings.Cut(strings.TrimRight(line, "\r"), "=")
		if !ok {
			continue
		}
		v = strings.TrimSpace(v)
		switch k {
		case "hostname":
			f.Hostname = v
		case "os":
			f.OS = v
		case "arch":
			f.Arch = v
		case "ips":
			for _, ip := range strings.Fields(v) {
				if !strings.Contains(ip, ":") { // keep IPv4: easier to type, works in URLs as is
					f.IPs = append(f.IPs, ip)
				}
			}
		case "docker":
			f.Docker = v
		case "kubectl":
			f.Kubectl = v
		case "k8s_node":
			f.K8sNode = v
		case "keel":
			f.Keel = v == "1"
		case "docker_existing": // name|image|hostport
			p := strings.Split(v, "|")
			if len(p) >= 2 && p[0] != "" {
				e := &ExistingDocker{Name: p[0], Image: p[1]}
				if len(p) > 2 {
					e.Port, _ = strconv.Atoi(p[2])
				}
				f.ExistingDocker = e
			}
		case "k8s_existing": // ns/name|container|image|strategy
			p := strings.Split(v, "|")
			ns, name, ok := strings.Cut(p[0], "/")
			if ok && len(p) >= 4 {
				f.ExistingK8s = &ExistingK8s{Namespace: ns, Name: name, Container: p[1], Image: p[2], Strategy: p[3]}
			}
		case "k8s_hosts":
			if f.ExistingK8s != nil {
				f.ExistingK8s.Hosts = uniq(strings.Fields(v))
			}
		case "k8s_existing_nodeports":
			if f.ExistingK8s != nil {
				for _, s := range strings.Fields(v) {
					if n, err := strconv.Atoi(s); err == nil && n > 0 {
						f.ExistingK8s.NodePorts = append(f.ExistingK8s.NodePorts, n)
					}
				}
			}
		case "tailscale_dns":
			f.TailscaleDNS = strings.TrimSuffix(v, ".")
		case "tailscale_https":
			f.TailscaleHTTPSIn = v == "1"
		case "listening":
			for _, s := range strings.Fields(v) {
				if n, err := strconv.Atoi(s); err == nil {
					f.Listening[n] = true
				}
			}
		case "nodeports":
			for _, s := range strings.Fields(v) {
				if n, err := strconv.Atoi(s); err == nil {
					f.NodePorts[n] = true
				}
			}
		default:
			if path, ok := strings.CutPrefix(k, "free:"); ok {
				if n, err := strconv.ParseInt(v, 10, 64); err == nil {
					f.FreeKB[path] = n
				}
			}
		}
	}
	return f
}

func uniq(in []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, s := range in {
		if s != "" && !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

// Plan is what the user chose, resolved against the facts.
type Plan struct {
	// Adopt keeps the GetSetMix already on the server (Facts.Existing*):
	// it only turns on updates, updates it once and pairs this computer.
	Adopt bool
	// Target is "docker" or "kubernetes".
	Target        string
	InstallDocker bool // Docker is missing: install it with get.docker.com
	Image         string
	// Pull is false for an image that only exists locally (testing a build).
	Pull       bool
	DataDir    string
	MusicDir   string
	Port       int // Docker host port, or the Kubernetes NodePort
	AutoUpdate bool
	Language   string // "en" | "it"

	// Tailscale turns on HTTPS with `tailscale serve`, on TailscalePort.
	Tailscale     bool
	TailscalePort int

	// Token pairs this computer; Label names it in link-tokens.
	Token string
	Label string

	Facts Facts
}

// Defaults fills a plan's blanks from the facts: the target the server can
// run, free ports, the HTTPS port Tailscale has free.
func (p *Plan) Defaults() {
	f := p.Facts
	if p.Image == "" {
		p.Image = DefaultImage
		p.Pull = true
	}
	if p.DataDir == "" {
		p.DataDir = DefaultDataDir
	}
	if p.MusicDir == "" {
		p.MusicDir = DefaultMusicDir
	}
	if p.Language == "" {
		p.Language = "en"
	}
	if p.Target == "" {
		switch {
		case f.ExistingK8s != nil && p.Adopt:
			p.Target = "kubernetes"
		case f.ExistingDocker != nil && p.Adopt:
			p.Target = "docker"
		case f.Docker != "":
			p.Target = "docker"
		case f.Kubectl != "":
			p.Target = "kubernetes"
		default:
			p.Target = "docker"
			p.InstallDocker = true
		}
	}
	if p.Port == 0 && p.Adopt {
		switch {
		case p.Target == "docker" && f.ExistingDocker != nil:
			p.Port = f.ExistingDocker.Port
		case p.Target == "kubernetes" && f.ExistingK8s != nil && len(f.ExistingK8s.NodePorts) > 0:
			p.Port = f.ExistingK8s.NodePorts[0]
		}
	}
	if p.Port == 0 && !p.Adopt {
		if p.Target == "kubernetes" {
			p.Port = freePort(DefaultNodePort, f.NodePorts)
		} else {
			p.Port = freePort(DefaultPort, f.Listening)
		}
	}
	if p.TailscalePort == 0 {
		p.TailscalePort = 443
		if f.TailscaleHTTPSIn {
			p.TailscalePort = 8443
		}
	}
}

func freePort(start int, used map[int]bool) int {
	for p := start; p < start+50; p++ {
		if !used[p] {
			return p
		}
	}
	return start
}

var (
	labelSafe = regexp.MustCompile(`[^A-Za-z0-9 ._-]+`)
	tokenSafe = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
	pathSafe  = regexp.MustCompile(`^/[A-Za-z0-9 ._/+-]*$`)
	imageSafe = regexp.MustCompile(`^[a-z0-9][a-z0-9./:_@-]*$`)
	nameSafe  = regexp.MustCompile(`^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$`)
	dockName  = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]*$`)
)

// Kubectls are the only commands Facts.Kubectl may name: it is run unquoted.
var Kubectls = []string{"kubectl", "microk8s kubectl", "k3s kubectl"}

// Validate refuses plans that would put user input into the script unsafely
// or that the server can't run.
func (p *Plan) Validate() error {
	if !tokenSafe.MatchString(p.Token) {
		return fmt.Errorf("bad link token")
	}
	for _, d := range []string{p.DataDir, p.MusicDir} {
		if !pathSafe.MatchString(d) || strings.Contains(d, "..") || d == "/" {
			return fmt.Errorf("%q is not a folder the setup can use: use an absolute path like /srv/music", d)
		}
	}
	switch {
	case p.Adopt && p.Target == "docker" && p.Facts.ExistingDocker == nil,
		p.Adopt && p.Target == "kubernetes" && p.Facts.ExistingK8s == nil:
		return fmt.Errorf("there is no GetSetMix on this server to keep")
	case p.Target == "kubernetes" && p.Facts.Kubectl == "":
		return fmt.Errorf("this server has no Kubernetes this setup can reach")
	case p.Target != "docker" && p.Target != "kubernetes":
		return fmt.Errorf("unknown target %q", p.Target)
	}
	if !imageSafe.MatchString(p.Image) {
		return fmt.Errorf("bad image %q", p.Image)
	}
	if p.Target == "kubernetes" && !slices.Contains(Kubectls, p.Facts.Kubectl) {
		return fmt.Errorf("unexpected kubectl %q", p.Facts.Kubectl)
	}
	if e := p.Facts.ExistingK8s; p.Adopt && e != nil && p.Target == "kubernetes" &&
		!(nameSafe.MatchString(e.Namespace) && nameSafe.MatchString(e.Name) && nameSafe.MatchString(e.Container)) {
		return fmt.Errorf("unexpected deployment name %s/%s", e.Namespace, e.Name)
	}
	if e := p.Facts.ExistingDocker; p.Adopt && e != nil && p.Target == "docker" && !dockName.MatchString(e.Name) {
		return fmt.Errorf("unexpected container name %q", e.Name)
	}
	if p.Facts.K8sNode != "" && !nameSafe.MatchString(p.Facts.K8sNode) {
		return fmt.Errorf("unexpected node name %q", p.Facts.K8sNode)
	}
	if p.Language != "en" && p.Language != "it" {
		return fmt.Errorf("unknown language %q", p.Language)
	}
	if (!p.Adopt || p.Tailscale) && (p.Port < 1 || p.Port > 65535) {
		return fmt.Errorf("bad port %d", p.Port)
	}
	return nil
}

// Steps are the checklist the wizard shows, in order, for a plan.
func (p *Plan) Steps() []string {
	var s []string
	if p.InstallDocker {
		s = append(s, "docker")
	}
	switch {
	case p.Adopt && p.Target == "kubernetes":
		s = append(s, "updates", "app") // updates also sets the pull policy the update relies on
	case p.Adopt && p.AutoUpdate:
		s = append(s, "updates", "app")
	case p.Adopt:
		s = append(s, "app")
	case p.AutoUpdate:
		s = append(s, "folders", "app", "updates")
	default:
		s = append(s, "folders", "app")
	}
	s = append(s, "start", "link")
	if p.Tailscale {
		s = append(s, "https")
	}
	return s
}

// q quotes a string for POSIX sh.
func q(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }

var funcs = template.FuncMap{
	"q":     q,
	"label": func(s string) string { return strings.TrimSpace(labelSafe.ReplaceAllString(s, "")) },
	"keel":  func() string { return keelManifest },
	"json":  func(s string) string { return strings.ReplaceAll(strings.ReplaceAll(s, `\`, `\\`), `"`, `\"`) },
}

var (
	bootstrapT = template.Must(template.New("bootstrap").Delims("[[", "]]").Funcs(funcs).Parse(bootstrapSh))
	planT      = template.Must(template.New("plan").Delims("[[", "]]").Funcs(funcs).Parse(planSh))
)

// Bootstrap is the script the pasted command runs.
func Bootstrap(base string) string {
	var b bytes.Buffer
	if err := bootstrapT.Execute(&b, map[string]string{"Base": base}); err != nil {
		panic(err) // the template is static: a failure is a bug
	}
	return b.String()
}

// Script is the installation for a validated plan.
func Script(base string, p Plan) (string, error) {
	if err := p.Validate(); err != nil {
		return "", err
	}
	data := struct {
		Plan
		Base, Kubectl, Container, Watchtower, Scope, Namespace, Name, Steps string
	}{
		Plan: p, Base: base, Kubectl: p.Facts.Kubectl,
		Container: containerName, Watchtower: WatchtowerImage, Scope: WatchtowerScope,
		Namespace: defaultNamespace, Name: containerName,
		Steps: strings.Join(p.Steps(), " "),
	}
	if p.Adopt && p.Target == "docker" {
		data.Container = p.Facts.ExistingDocker.Name
	}
	if p.Adopt && p.Target == "kubernetes" {
		data.Namespace = p.Facts.ExistingK8s.Namespace
		data.Name = p.Facts.ExistingK8s.Name
	}
	var b bytes.Buffer
	if err := planT.Execute(&b, data); err != nil {
		return "", err
	}
	return b.String(), nil
}
