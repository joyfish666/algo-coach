import js from '@eslint/js'
import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'

export default [
  {
    ignores: ['dist/**', 'node_modules/**', '*.config.js'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      // formatting is not enforced here; keep the linter to correctness-class
      // issues (unused vars, undefined refs, vue template errors)
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'no-empty': ['error', { allowEmptyCatch: true }],
      // view files are named after their route (Problems.vue, Setup.vue);
      // renaming them would fight vue-router conventions
      'vue/multi-word-component-names': 'off',
    },
  },
]
