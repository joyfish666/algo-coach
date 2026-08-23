<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { basicSetup, EditorView } from 'codemirror'
import { Compartment, EditorState } from '@codemirror/state'
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

const languages = {
  cpp,
  python3: python,
  java,
}

let view = null

function languageExtensionOf(slug) {
  const factory = languages[slug]
  return factory ? [factory()] : []
}

onMounted(() => {
  view = new EditorView({
    parent: container.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        languageCompartment.of(languageExtensionOf(props.lang)),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
        }),
      ],
    }),
  })
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
  if (view) view.destroy()
})
</script>

<template>
  <div ref="container" class="code-editor"></div>
</template>

<style scoped>
.code-editor {
  border: 1px solid var(--gray-neutral);
  border-radius: var(--radius-card);
  overflow: hidden;
  text-align: left;
}
</style>
