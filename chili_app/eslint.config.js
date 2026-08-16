import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // `knowledgeBaseSituation` is a pure helper colocated with the component
    // it drives (spec Task 8), exported so it can be unit-tested directly
    // without rendering. It is not a component, but this file has no other
    // consumer than its own test, so the fast-refresh boundary this rule
    // protects is never actually at stake here.
    files: ['src/features/kb/overview/OverviewSection.tsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        { allowExportNames: ['knowledgeBaseSituation'] },
      ],
    },
  },
])
