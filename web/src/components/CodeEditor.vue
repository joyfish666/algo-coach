<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup, EditorView } from 'codemirror'
import { Compartment, EditorState } from '@codemirror/state'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags } from '@lezer/highlight'
import { cpp } from '@codemirror/lang-cpp'
import { java } from '@codemirror/lang-java'
import { python } from '@codemirror/lang-python'

const props = defineProps({
  modelValue: { type: String, default: '' },
  lang: { type: String, default: 'cpp' },
})
const emit = defineEmits(['update:modelValue'])

const container = ref(null)
const languageCompartment = new Compartment()
const themeCompartment = new Compartment()

// basicSetup ships a light-only highlight palette; in dark mode its colors
// sat on a dark background with poor contrast. Both palettes below use the
// app's own token values; the chrome (background/gutter/cursor) is themed
// through CSS variables so it follows the data-theme switch automatically.
const lightHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: '#7c3aed' },
  { tag: [tags.controlKeyword, tags.moduleKeyword], color: '#7c3aed' },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName, tags.macroName], color: '#212121' },
  { tag: [tags.variableName], color: '#212121' },
  { tag: [tags.function(tags.variableName), tags.labelName], color: '#1d4ed8' },
  { tag: [tags.color, tags.constant(tags.name), tags.standard(tags.name)], color: '#0e7490' },
  { tag: [tags.definition(tags.name), tags.separator], color: '#212121' },
  { tag: [tags.typeName, tags.className, tags.number, tags.changed, tags.annotation, tags.self, tags.namespace], color: '#b45309' },
  { tag: [tags.operator, tags.operatorKeyword], color: '#334155' },
  { tag: [tags.url, tags.escape, tags.regexp, tags.link], color: '#0e7490' },
  { tag: [tags.meta, tags.comment], color: '#6b7280' },
  { tag: tags.strong, fontWeight: 'bold' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.link, color: '#2563eb', textDecoration: 'underline' },
  { tag: tags.heading, fontWeight: 'bold', color: '#212121' },
])

const darkHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: '#c4b5fd' },
  { tag: [tags.controlKeyword, tags.moduleKeyword], color: '#c4b5fd' },
  { tag: [tags.name, tags.deleted, tags.character, tags.propertyName, tags.macroName], color: '#e5e5e5' },
  { tag: [tags.variableName], color: '#e5e5e5' },
  { tag: [tags.function(tags.variableName), tags.labelName], color: '#93c5fd' },
  { tag: [tags.color, tags.constant(tags.name), tags.standard(tags.name)], color: '#67e8f9' },
  { tag: [tags.definition(tags.name), tags.separator], color: '#e5e5e5' },
  { tag: [tags.typeName, tags.className, tags.number, tags.changed, tags.annotation, tags.self, tags.namespace], color: '#fcd34d' },
  { tag: [tags.operator, tags.operatorKeyword], color: '#cbd5e1' },
  { tag: [tags.url, tags.escape, tags.regexp, tags.link], color: '#67e8f9' },
  { tag: [tags.meta, tags.comment], color: '#9ca3af' },
  { tag: tags.strong, fontWeight: 'bold' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.link, color: '#93c5fd', textDecoration: 'underline' },
  { tag: tags.heading, fontWeight: 'bold', color: '#e5e5e5' },
])

function isDarkTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark'
}

function themeExtensions() {
  return syntaxHighlighting(isDarkTheme() ? darkHighlight : lightHighlight)
}

let observer = null
let view = null

function languageExtensionOf(slug) {
  const factory = languages[slug]
  return factory ? [factory()] : []
}

const languages = {
  cpp,
  python3: python,
  java,
}

onMounted(() => {
  view = new EditorView({
    parent: container.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        languageCompartment.of(languageExtensionOf(props.lang)),
        themeCompartment.of(themeExtensions()),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
        }),
      ],
    }),
  })

  // follow the app-wide light/dark switch without owning it: the <html>
  // data-theme attribute is the single source of truth
  observer = new MutationObserver(() => {
    if (view) {
      view.dispatch({ effects: themeCompartment.reconfigure(themeExtensions()) })
    }
  })
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

watch(
  () => props.lang,
  (slug) => {
    if (view) {
      view.dispatch({ effects: languageCompartment.reconfigure(languageExtensionOf(slug)) })
    }
  },
)

watch(
  () => props.modelValue,
  (value) => {
    if (!view) return
    const current = view.state.doc.toString()
    if (value !== current) {
      view.dispatch({ changes: { from: 0, to: current.length, insert: value } })
    }
  },
)

onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (view) view.destroy()
})
</script>

<template>
  <div ref="container" class="code-editor"></div>
</template>

<style scoped>
.code-editor {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  overflow: hidden;
  text-align: left;
}
</style>

<style>
/* editor chrome follows the design tokens so both themes render correctly;
   global (unscoped) because CodeMirror mounts its own DOM */
.code-editor .cm-editor {
  background: var(--bg-primary);
  color: var(--text-primary);
}

.code-editor .cm-gutters {
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-subtle);
  color: var(--gray-neutral);
}

.code-editor .cm-activeLineGutter,
.code-editor .cm-activeLine {
  background: var(--bg-secondary);
}

.code-editor .cm-selectionBackground,
.code-editor .cm-content ::selection {
  background: rgba(37, 99, 235, 0.25) !important;
}
</style>
