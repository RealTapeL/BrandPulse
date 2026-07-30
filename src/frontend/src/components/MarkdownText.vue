<template>
  <!-- 轻量 markdown 渲染：先整体 HTML 转义，再按规则还原基本语法，天然防 XSS -->
  <div class="md-body" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
})

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInline(s) {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}

function render(src) {
  const lines = escapeHtml(src).split('\n')
  const out = []
  let listType = null // 'ul' | 'ol'
  let inCode = false
  let codeBuf = []

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }

  for (const raw of lines) {
    const line = raw
    //  fenced code block
    if (/^```/.test(line.trim())) {
      if (inCode) {
        out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`)
        codeBuf = []
        inCode = false
      } else {
        closeList()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }

    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) {
      closeList()
      const level = h[1].length
      out.push(`<h${level}>${renderInline(h[2])}</h${level}>`)
      continue
    }

    if (/^>\s?/.test(line)) {
      closeList()
      out.push(`<blockquote>${renderInline(line.replace(/^>\s?/, ''))}</blockquote>`)
      continue
    }

    const ul = line.match(/^\s*[-*]\s+(.*)$/)
    if (ul) {
      if (listType !== 'ul') {
        closeList()
        out.push('<ul>')
        listType = 'ul'
      }
      out.push(`<li>${renderInline(ul[1])}</li>`)
      continue
    }

    const ol = line.match(/^\s*\d+\.\s+(.*)$/)
    if (ol) {
      if (listType !== 'ol') {
        closeList()
        out.push('<ol>')
        listType = 'ol'
      }
      out.push(`<li>${renderInline(ol[1])}</li>`)
      continue
    }

    closeList()
    if (line.trim() === '') {
      out.push('')
    } else {
      out.push(`<p>${renderInline(line)}</p>`)
    }
  }
  closeList()
  if (inCode) out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`)
  return out.join('\n')
}

const html = computed(() => render(props.text || ''))
</script>
