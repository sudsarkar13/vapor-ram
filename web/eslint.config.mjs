import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Static export output. It is committed (the Python package serves it
    // directly) but it is minified build artefact, not source -- linting it
    // reports thousands of issues in generated code.
    "dist/**",
  ]),
  {
    // components/ui/** is scaffolding emitted by the shadcn CLI and is
    // regenerated wholesale by `shadcn add`, so local edits there do not
    // survive. Report its effect-pattern findings as warnings instead of
    // failing the build on third-party generated code.
    files: ["components/ui/**"],
    rules: {
      "react-hooks/set-state-in-effect": "warn",
    },
  },
]);

export default eslintConfig;
