<template>
  <div class="report-download">
    <button
      class="report-download__btn"
      @click.stop="showMenu = !showMenu"
      aria-haspopup="menu"
      :aria-expanded="showMenu"
    >⬇ Download <span class="caret">{{ showMenu ? '▲' : '▼' }}</span></button>
    <template v-if="showMenu">
      <div class="report-download__overlay" @click="showMenu = false"></div>
      <div class="report-download__menu" role="menu" aria-label="Download format">
        <button class="report-download__item" role="menuitem" @click="onDownload('docx')">
          <span class="dl-ic docx">W</span>
          <span class="dl-text"><span class="dl-t">Word</span><span class="dl-s">.docx — share</span></span>
        </button>
        <button class="report-download__item" role="menuitem" @click="onDownload('md')">
          <span class="dl-ic md">M</span>
          <span class="dl-text"><span class="dl-t">Markdown</span><span class="dl-s">.md — raw</span></span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { downloadReport } from '../api/report'

const props = defineProps({
  reportId: { type: String, required: true }
})

const emit = defineEmits(['download-error'])

const showMenu = ref(false)

const onDownload = async (format) => {
  showMenu.value = false
  if (!props.reportId) return
  try {
    const { blob, filename } = await downloadReport(props.reportId, format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename // 服务端提供的真实名称：report_<原始文件名>.<格式>
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    emit('download-error', err?.message || String(err))
  }
}
</script>

<style scoped>
.report-download { position: relative; flex: none; }
.report-download__btn {
  display: inline-flex; align-items: center; gap: 8px;
  background: #111; color: #fff; border: none; border-radius: 8px;
  padding: 8px 14px; font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.report-download__btn .caret { font-size: 9px; opacity: .85; }
.report-download__btn:focus-visible { outline: 2px solid #FF5722; outline-offset: 2px; }
.report-download__overlay { position: fixed; inset: 0; z-index: 40; }
.report-download__menu {
  position: absolute; top: calc(100% + 8px); right: 0; z-index: 41;
  background: #fff; border: 1px solid #E5E7EB; border-radius: 10px;
  box-shadow: 0 10px 28px rgba(0,0,0,.14); width: 220px; overflow: hidden;
}
.report-download__item {
  display: flex; align-items: center; gap: 11px; width: 100%;
  padding: 11px 14px; font-size: 13px; text-align: left;
  background: #fff; border: 0; border-bottom: 1px solid #F3F4F6; cursor: pointer;
}
.report-download__item:last-child { border-bottom: none; }
.report-download__item:hover { background: #FAFAFA; }
.report-download__item:focus-visible { background: #FFF4EF; outline: 2px solid #FF5722; outline-offset: -2px; }
.dl-ic {
  width: 26px; height: 26px; border-radius: 6px; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 800; color: #fff; flex: none;
}
.dl-ic.docx { background: #2B579A; }
.dl-ic.md { background: #111; }
.dl-text { display: flex; flex-direction: column; }
.dl-t { font-weight: 600; line-height: 1.2; }
.dl-s { font-size: 11px; color: #666; }
</style>
