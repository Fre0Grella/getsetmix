package setup

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

var updateTokens = flag.Bool("update", false, "rewrite ui/tokens.css from the app's styles.css")

// sharedTokens are the colours the Setup window takes from the app; the
// rest of setup.css (the rail, the washes, the code block, its fonts) is
// its own.
var sharedTokens = []string{
	"bg", "surface", "hover", "field", "line", "line-soft", "text", "text-2", "text-3",
	"accent", "accent-hi", "on-accent", "accent-wash", "ok", "warn", "danger", "scrim", "shadow",
}

var tokenLine = regexp.MustCompile(`^\s*--([a-z0-9-]+):\s*(.+?);\s*(/\*.*)?$`)

// block returns the custom properties of the rule that starts with head.
func block(css, head string) (map[string]string, error) {
	i := strings.Index(css, head)
	if i < 0 {
		return nil, fmt.Errorf("no %q in the app's styles.css", head)
	}
	body := css[i+len(head):]
	body = body[:strings.Index(body, "\n}")]
	props := map[string]string{}
	for _, line := range strings.Split(body, "\n") {
		if m := tokenLine.FindStringSubmatch(line); m != nil {
			props[m[1]] = m[2]
		}
	}
	return props, nil
}

// appTokens is ui/tokens.css as it must be: the shared colours of the app,
// light by default and dark with the system (Setup has no theme switch).
func appTokens(css string) (string, error) {
	light, err := block(css, ":root {")
	if err != nil {
		return "", err
	}
	dark, err := block(css, `:root[data-theme="dark"] {`)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	b.WriteString("/* The colours the Setup window shares with the app, copied from\n" +
		"   app/static/styles.css by `go generate ./internal/setup`. Do not edit:\n" +
		"   TestTokensMatchTheApp fails when this copy and the app differ. */\n:root {\n")
	for _, name := range sharedTokens {
		v, ok := light[name]
		if !ok {
			return "", fmt.Errorf("the app has no light --%s", name)
		}
		fmt.Fprintf(&b, "  --%s: %s;\n", name, v)
	}
	b.WriteString("}\n\n@media (prefers-color-scheme: dark) {\n  :root {\n")
	for _, name := range sharedTokens {
		v, ok := dark[name]
		if !ok {
			v = light[name] // a token the dark theme does not change
		}
		fmt.Fprintf(&b, "    --%s: %s;\n", name, v)
	}
	b.WriteString("  }\n}\n")
	return b.String(), nil
}

// The Setup window's colours are the app's: a copy that drifted (it did,
// before this test) fails here. `go generate ./internal/setup` rewrites it.
func TestTokensMatchTheApp(t *testing.T) {
	src, err := os.ReadFile(filepath.Join("..", "..", "..", "app", "static", "styles.css"))
	if err != nil {
		t.Fatal(err)
	}
	want, err := appTokens(string(src))
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join("ui", "tokens.css")
	if *updateTokens {
		if err := os.WriteFile(path, []byte(want), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	// A Windows checkout may turn the copy's line endings into CRLF.
	if strings.ReplaceAll(string(got), "
", "
") != want {
		t.Fatalf("ui/tokens.css differs from the app's colours: run `go generate ./internal/setup`")
	}
}
