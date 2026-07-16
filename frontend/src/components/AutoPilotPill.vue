<template>
  <span v-if="active" class="autopilot-pill">
    <span class="zap">⚡</span>
    <span class="lbl">{{ $t('autoPilot.pill') }}</span>
    <button class="exit" @click="exit">{{ $t('autoPilot.exit') }}</button>
  </span>
</template>

<script setup>
import { ref } from 'vue'
import { isAutoPilot, disableAutoPilot } from '../utils/autoPilot'

const active = ref(isAutoPilot())

const exit = () => {
  disableAutoPilot()
  active.value = false
}
</script>

<style scoped>
.autopilot-pill {
  display: inline-flex; align-items: center; gap: 9px;
  background: #FFF3EE; border: 1px solid #FFD0BD; border-radius: 20px;
  padding: 5px 6px 5px 12px; font-size: 11px; font-weight: 700;
  color: #C2410C; letter-spacing: .03em; white-space: nowrap;
}
.autopilot-pill .zap { font-size: 12px; }
.autopilot-pill .exit {
  border: 1px solid #FFD0BD; border-radius: 14px; background: #fff;
  color: #C2410C; font-size: 10.5px; font-weight: 600; padding: 3px 10px;
  cursor: pointer; font-family: inherit;
}
.autopilot-pill .exit:hover { background: #C2410C; color: #fff; }
</style>
