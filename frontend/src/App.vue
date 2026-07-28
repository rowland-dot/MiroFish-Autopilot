<template>
  <router-view />
</template>

<script setup>
// 使用 Vue Router 来管理页面
// 全局流水线驱动器：跨页面存活，自动推进排队中的自动驾驶项目
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { startDriver } from './services/pipelineDriver'
import { pipelineStore } from './store/pipelineQueue'
import { targetRouteForEntry, observedEntry, shouldFollow } from './utils/observeFollow'

const route = useRoute()
const router = useRouter()

onMounted(() => {
  startDriver()
})

// 观察模式跟随：步骤页已改为只读（不再自我推进，否则会与驱动器重复触发），
// 因此在 ?observe=1 时由这里跟着流水线阶段自动切页——只切视图，不驱动任何流程。
watch(
  () => [route.fullPath, pipelineStore.entries.value],
  () => {
    if (route.query.observe !== '1') return
    const entry = observedEntry(pipelineStore.entries.value, route.name, route.params)
    const target = targetRouteForEntry(entry)
    if (shouldFollow(target, route.name, route.params)) router.replace(target)
  },
  { deep: true }
)
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #000000;
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}
</style>
