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
