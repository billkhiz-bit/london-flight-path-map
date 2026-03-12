import html from 'eslint-plugin-html';
import js from '@eslint/js';
import security from 'eslint-plugin-security';
import globals from 'globals';

export default [
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
