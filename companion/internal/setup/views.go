package setup

import (
	"strings"

	"github.com/Fre0Grella/getsetmix/companion/internal/serverscript"
)

// factsView is the server as the UI shows it.
type factsView struct {
	Hostname   string             `json:"hostname"`
	OS         string             `json:"os"`
	Arch       string             `json:"arch"`
	IPs        []string           `json:"ips"`
	Docker     string             `json:"docker,omitempty"`
	Kubernetes string             `json:"kubernetes,omitempty"` // MicroK8s | k3s | Kubernetes
	Existing   *existingView      `json:"existing,omitempty"`
	Tailscale  string             `json:"tailscale,omitempty"`
	FreeGB     map[string]float64 `json:"freeGB"`
	Defaults   defaultsView       `json:"defaults"`
}

type existingView struct {
	Kind  string `json:"kind"` // docker | kubernetes
	Where string `json:"where"`
	Image string `json:"image"`
	Port  int    `json:"port,omitempty"`
	Host  string `json:"host,omitempty"`
}

type defaultsView struct {
	Target        string `json:"target"`
	MusicDir      string `json:"musicDir"`
	InstallDocker bool   `json:"installDocker"`
}

func viewFacts(f serverscript.Facts) *factsView {
	v := &factsView{Hostname: f.Hostname, OS: f.OS, Arch: f.Arch, IPs: f.IPs, Docker: f.Docker,
		Tailscale: f.TailscaleDNS, FreeGB: map[string]float64{}}
	switch {
	case strings.HasPrefix(f.Kubectl, "microk8s"):
		v.Kubernetes = "MicroK8s"
	case strings.HasPrefix(f.Kubectl, "k3s"):
		v.Kubernetes = "k3s"
	case f.Kubectl != "":
		v.Kubernetes = "Kubernetes"
	}
	if e := f.ExistingK8s; e != nil {
		v.Existing = &existingView{Kind: "kubernetes", Where: e.Namespace + "/" + e.Name, Image: e.Image}
		if len(e.Hosts) > 0 {
			v.Existing.Host = e.Hosts[0]
		}
		if len(e.NodePorts) > 0 {
			v.Existing.Port = e.NodePorts[0]
		}
	} else if e := f.ExistingDocker; e != nil {
		v.Existing = &existingView{Kind: "docker", Where: e.Name, Image: e.Image, Port: e.Port}
	}
	for path, kb := range f.FreeKB {
		v.FreeGB[path] = float64(kb) / (1 << 20)
	}
	p := serverscript.Plan{Facts: f, Adopt: f.ExistingK8s != nil || f.ExistingDocker != nil}
	p.Defaults()
	v.Defaults = defaultsView{Target: p.Target, MusicDir: p.MusicDir, InstallDocker: p.InstallDocker}
	return v
}

// planV is the chosen plan as the UI shows it.
type planV struct {
	Adopt         bool     `json:"adopt"`
	Target        string   `json:"target"`
	Steps         []string `json:"steps"`
	Port          int      `json:"port"`
	Tailscale     bool     `json:"tailscale"`
	AutoUpdate    bool     `json:"autoUpdate"`
	MusicDir      string   `json:"musicDir"`
	InstallDocker bool     `json:"installDocker"`
}

func viewPlan(p serverscript.Plan) *planV {
	return &planV{Adopt: p.Adopt, Target: p.Target, Steps: p.Steps(), Port: p.Port, Tailscale: p.Tailscale,
		AutoUpdate: p.AutoUpdate, MusicDir: p.MusicDir, InstallDocker: p.InstallDocker}
}
