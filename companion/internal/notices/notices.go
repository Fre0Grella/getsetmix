// Package notices carries the license texts that ship with the companion and
// GetSetMix Setup: the project's AGPL-3.0 text and THIRD-PARTY-NOTICES.md.
//
// go:embed cannot reach above the module directory, so the two files here are
// copies of the ones at the repository root. TestCopiesMatchTheRepositoryRoot
// fails when they drift (companion.yml runs it whenever the root files change);
// `go generate ./internal/notices` refreshes them.
package notices

import (
	_ "embed"
	"strings"
)

//go:generate sh -c "cp ../../../LICENSE ../../../THIRD-PARTY-NOTICES.md ."

//go:embed LICENSE
var license string

//go:embed THIRD-PARTY-NOTICES.md
var thirdParty string

// License is the full AGPL-3.0 text GetSetMix is released under.
func License() string { return license }

// Notices is THIRD-PARTY-NOTICES.md.
func Notices() string { return thirdParty }

// Text is what "licenses" shows: the third-party notices, then the license
// text of GetSetMix itself.
func Text() string {
	return strings.TrimRight(thirdParty, "\n") +
		"\n\n---\n\nGetSetMix itself is AGPL-3.0-only. Full text:\n\n" + license
}
