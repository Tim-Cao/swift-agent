<template>
  <div class="markdown-view" v-html="rendered"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github.css'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)

marked.setOptions({
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true,
})

const props = defineProps({ content: { type: String, default: '' } })

const rendered = computed(() => {
  const html = marked.parse(props.content || '')
  return DOMPurify.sanitize(html)
})
</script>

<style>
.markdown-view {
  line-height: 1.65;
  word-break: break-word;
  color: var(--n-text);
}
.markdown-view pre {
  background: var(--n-bg-code);
  border: 1px solid var(--n-border-light);
  padding: var(--n-gap) var(--n-gap);
  border-radius: var(--n-radius);
  overflow-x: auto;
}
.markdown-view code {
  background: var(--n-bg-code);
  color: #eb5757;
  padding: 1px 4px;
  border-radius: var(--n-radius-sm);
  font-family: var(--n-font-mono);
  font-size: 0.88em;
}
.markdown-view pre code {
  background: transparent;
  color: inherit;
  padding: 0;
}
.markdown-view ul,
.markdown-view ol {
  padding-left: 1.5em;
}
.markdown-view a {
  color: var(--n-accent);
}
.markdown-view table {
  border-collapse: collapse;
  width: 100%;
  display: block;
  overflow-x: auto;
}
.markdown-view th,
.markdown-view td {
  border: 1px solid var(--n-border);
  padding: 5px 8px;
  font-size: var(--n-text-sm);
}
.markdown-view th {
  background: var(--n-bg-code);
  font-weight: 600;
}
.markdown-view blockquote {
  margin: var(--n-gap) 0;
  padding-left: var(--n-gap);
  border-left: 3px solid var(--n-border-strong);
  color: var(--n-text-secondary);
}
</style>
