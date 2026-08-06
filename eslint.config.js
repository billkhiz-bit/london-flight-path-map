import html from 'eslint-plugin-html';
import js from '@eslint/js';
import security from 'eslint-plugin-security';
import globals from 'globals';

export default [
  // Added 2026-08-03. Before this, the config declared ONLY `files: ['**/*.html']`,
  // so every .js and .mjs in the repo was linted by nothing at all — sw.js,
  // js/api-base.js, the tests/*.mjs harnesses, mobile/scripts/copy-web.mjs (the
  // file holding a live critical defect) and scripts/*.mjs. Paired with
  // `"lint": "eslint index.html"`, the gate covered one file and read as green
  // for the whole repo, which is the same shape as the two gates rewritten on
  // 2026-07-27.
  {
    files: ['**/*.{js,mjs}'],
    ignores: ['js/vendor/**', 'score-demo/vendor/**', 'mobile/www/**', 'node_modules/**'],
    plugins: { security },
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      ecmaVersion: 2022,
      sourceType: 'module',
    },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': 'warn',
      'no-undef': 'warn',
      'no-redeclare': 'error',
      'eqeqeq': ['warn', 'always'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'security/detect-eval-with-expression': 'error',
      'security/detect-unsafe-regex': 'warn',
    },
  },

  // Browser-extension sources (added 2026-08-06). Needs its own block for two
  // reasons the generic **/*.{js,mjs} block above cannot cover:
  //
  //   1. `chrome.*` is a WebExtension global, present in neither globals.browser
  //      nor globals.node, so every runtime/storage call would read as no-undef.
  //   2. Content scripts listed together in one manifest entry SHARE a single
  //      isolated-world scope — extract.js defines extractListing() and panel.js
  //      calls it, with no import between them. That is correct WebExtension
  //      code but looks like an undefined reference to a per-file linter. The
  //      two files carry `/* exported */` and `/* global */` directives to
  //      express that link; declaring it here instead would collide with the
  //      real definition (no-redeclare) in the file that owns it.
  //
  // sourceType is 'script', not 'module': content scripts are classic scripts.
  // The service worker IS a module (manifest declares type: 'module'), but it
  // imports nothing, so one block covers both without a parse error.
  {
    files: ['extension/**/*.js'],
    plugins: { security },
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.webextensions,
      },
      ecmaVersion: 2022,
      sourceType: 'script',
    },
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': 'warn',
      'no-undef': 'error',
      'no-redeclare': 'error',
      'eqeqeq': ['warn', 'always'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'security/detect-eval-with-expression': 'error',
      'security/detect-unsafe-regex': 'error',
    },
  },

  {
    files: ['**/*.html'],
    plugins: { html, security },
  },
  {
    files: ['**/*.html'],
    languageOptions: {
      globals: {
        ...globals.browser,
        d3: 'readonly',
      },
      ecmaVersion: 2022,
      sourceType: 'script',
    },
    rules: {
      // Code quality
      'no-unused-vars': 'warn',
      'no-undef': 'warn',
      'no-redeclare': 'error',
      'eqeqeq': ['warn', 'always'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-inner-declarations': 'off',
      'no-prototype-builtins': 'warn',
      'no-empty': 'warn',
      'no-console': 'off',
      // Security rules
      'security/detect-eval-with-expression': 'error',
      'security/detect-non-literal-regexp': 'warn',
      'security/detect-unsafe-regex': 'error',
      'security/detect-buffer-noassert': 'error',
      'security/detect-no-csrf-before-method-override': 'error',
      'security/detect-object-injection': 'off', // too noisy for bracket notation
    },
  },
];
