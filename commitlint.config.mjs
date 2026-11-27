// Conventional Commits are mandatory on main — semantic-release derives the
// release version from them (see pyproject.toml / .github/workflows/release.yml).
// Enforced in CI by .github/workflows/commitlint.yml (every commit, and the PR
// title that becomes the squash commit) and locally by the commit-msg hook in
// .pre-commit-config.yaml.
// NOTE: commitlint-github-action requires an ESM .mjs config (not .js).

// The headline is 50 characters at most, not counting the " (#NN)" a squash
// merge adds: GitHub's narrower views cut longer ones off.
const MAX_HEADLINE = 50;

export default {
  extends: ["@commitlint/config-conventional"],
  plugins: [
    {
      rules: {
        "headline-length": ({ header }) => {
          const headline = (header ?? "").replace(/ \(#\d+\)$/, "");
          return [
            headline.length <= MAX_HEADLINE,
            `the headline is ${headline.length} characters (without the PR number); keep it within ${MAX_HEADLINE}`,
          ];
        },
      },
    },
  ],
  rules: {
    "headline-length": [2, "always"],
  },
};
