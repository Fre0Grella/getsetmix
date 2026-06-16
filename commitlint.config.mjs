// Conventional Commits are mandatory on main — semantic-release derives the
// release version from them (see pyproject.toml / .github/workflows/release.yml).
// Enforced in CI by .github/workflows/commitlint.yml and locally by the
// commit-msg hook in .pre-commit-config.yaml.
// NOTE: commitlint-github-action requires an ESM .mjs config (not .js).
export default {
  extends: ["@commitlint/config-conventional"],
};
