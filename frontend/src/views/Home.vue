<template>
  <div class="home-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-brand">MIROFISH</div>
      <div class="nav-links">
        <LanguageSwitcher />
        <a href="https://github.com/666ghj/MiroFish" target="_blank" class="github-link">
          {{ $t('nav.visitGithub') }} <span class="arrow">↗</span>
        </a>
      </div>
    </nav>

    <div class="main-content">
      <!-- 折叠后的细条：只留品牌标签与展开按钮，工作区直接顶到首屏 -->
      <section v-if="bannerCollapsed" class="hero-collapsed">
        <span class="orange-tag">{{ $t('home.tagline') }}</span>
        <button class="banner-toggle" @click="toggleBanner" :title="$t('home.expandBanner')">
          {{ $t('home.expandBanner') }} <span class="chev">⌄</span>
        </button>
      </section>

      <!-- 上半部分：Hero 区域 -->
      <section v-else class="hero-section">
        <button class="banner-toggle banner-toggle-float" @click="toggleBanner" :title="$t('home.collapseBanner')">
          {{ $t('home.collapseBanner') }} <span class="chev up">⌃</span>
        </button>
        <div class="hero-left">
          <div class="tag-row">
            <span class="orange-tag">{{ $t('home.tagline') }}</span>
            <span class="version-text">{{ $t('home.version') }}</span>
          </div>
          
          <h1 class="main-title">
            {{ $t('home.heroTitle1') }}<br>
            <span class="gradient-text">{{ $t('home.heroTitle2') }}</span>
          </h1>
          
          <div class="hero-desc">
            <p>
              <i18n-t keypath="home.heroDesc" tag="span">
                <template #brand><span class="highlight-bold">{{ $t('home.heroDescBrand') }}</span></template>
                <template #agentScale><span class="highlight-orange">{{ $t('home.heroDescAgentScale') }}</span></template>
                <template #optimalSolution><span class="highlight-code">{{ $t('home.heroDescOptimalSolution') }}</span></template>
              </i18n-t>
            </p>
            <p class="slogan-text">
              {{ $t('home.slogan') }}<span class="blinking-cursor">_</span>
            </p>
          </div>
           
          <div class="decoration-square"></div>
        </div>
        
        <div class="hero-right">
          <!-- Logo 区域 -->
          <div class="logo-container">
            <img src="../assets/logo/MiroFish_logo_left.jpeg" alt="MiroFish Logo" class="hero-logo" />
          </div>
          
          <button class="scroll-down-btn" @click="scrollToBottom">
            ↓
          </button>
        </div>
      </section>

      <!-- 下半部分：双栏布局 -->
      <section class="dashboard-section">
        <!-- 左栏：状态与步骤 -->
        <div class="left-panel">
          <div class="panel-header">
            <span class="status-dot">■</span> {{ $t('home.systemStatus') }}
          </div>
          
          <h2 class="section-title">{{ $t('home.systemReady') }}</h2>
          <p class="section-desc">
            {{ $t('home.systemReadyDesc') }}
          </p>
          
          <!-- 数据指标卡片 -->
          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-value">{{ $t('home.metricLowCost') }}</div>
              <div class="metric-label">{{ $t('home.metricLowCostDesc') }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">{{ $t('home.metricHighAvail') }}</div>
              <div class="metric-label">{{ $t('home.metricHighAvailDesc') }}</div>
            </div>
          </div>

          <!-- 项目模拟步骤介绍 (新增区域) -->
          <div class="steps-container">
            <div class="steps-header">
               <span class="diamond-icon">◇</span> {{ $t('home.workflowSequence') }}
            </div>
            <div class="workflow-list">
              <div class="workflow-item">
                <span class="step-num">01</span>
                <div class="step-info">
                  <div class="step-title">{{ $t('home.step01Title') }}</div>
                  <div class="step-desc">{{ $t('home.step01Desc') }}</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">02</span>
                <div class="step-info">
                  <div class="step-title">{{ $t('home.step02Title') }}</div>
                  <div class="step-desc">{{ $t('home.step02Desc') }}</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">03</span>
                <div class="step-info">
                  <div class="step-title">{{ $t('home.step03Title') }}</div>
                  <div class="step-desc">{{ $t('home.step03Desc') }}</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">04</span>
                <div class="step-info">
                  <div class="step-title">{{ $t('home.step04Title') }}</div>
                  <div class="step-desc">{{ $t('home.step04Desc') }}</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">05</span>
                <div class="step-info">
                  <div class="step-title">{{ $t('home.step05Title') }}</div>
                  <div class="step-desc">{{ $t('home.step05Desc') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右栏：交互控制台 -->
        <div class="right-panel">
          <div class="console-box">
            <!-- 上传区域 -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">{{ $t('home.realitySeed') }}</span>
                <span class="console-meta">{{ $t('home.supportedFormats') }}</span>
              </div>
              
              <div 
                class="upload-zone"
                :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".pdf,.md,.txt,.docx"
                  @change="handleFileSelect"
                  style="display: none"
                  :disabled="loading"
                />
                
                <div v-if="files.length === 0" class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">{{ $t('home.dragToUpload') }}</div>
                  <div class="upload-hint">{{ $t('home.orBrowse') }}</div>
                </div>
                
                <div v-else class="file-list">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 分割线 -->
            <div class="console-divider">
              <span>{{ $t('home.inputParams') }}</span>
            </div>

            <!-- 输入区域 -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">{{ $t('home.simulationPrompt') }}</span>
                <!-- 历史提示词按钮：无可用历史时完全隐藏 -->
                <button
                  v-if="promptHistory.length"
                  class="prompt-history-btn"
                  @click.stop="showPromptHistory = !showPromptHistory"
                >
                  <span class="ph-ic">↺</span>
                  {{ $t('home.promptHistoryBtn', { count: promptHistory.length }) }}
                </button>
              </div>
              <div class="input-wrapper">
                <!-- 历史提示词浮层：覆盖在输入框上方，不改变页面布局 -->
                <template v-if="showPromptHistory">
                  <div class="prompt-history-backdrop" @click="showPromptHistory = false"></div>
                  <div class="prompt-history-panel">
                    <div class="php-head">
                      <span class="php-title">{{ $t('home.promptHistoryTitle') }} · {{ promptHistory.length }}</span>
                      <span class="php-actions">
                        <button class="php-clear" @click="clearAllPrompts">{{ $t('home.promptHistoryClearAll') }}</button>
                        <button class="php-close" @click="showPromptHistory = false">✕</button>
                      </span>
                    </div>
                    <div class="php-list">
                      <div
                        v-for="p in promptHistory"
                        :key="p.text"
                        class="php-item"
                        @click="usePrompt(p)"
                      >
                        <div class="php-text">{{ p.text }}</div>
                        <div class="php-meta">{{ p.date }}<template v-if="p.simulationId"> · {{ p.simulationId }}</template></div>
                        <button
                          class="php-remove"
                          :title="$t('home.promptHistoryHide')"
                          @click.stop="hidePrompt(p)"
                        >✕</button>
                      </div>
                    </div>
                    <div class="php-foot">{{ $t('home.promptHistoryFoot', { cap: PROMPT_CAP }) }}</div>
                  </div>
                </template>
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  :placeholder="$t('home.promptPlaceholder')"
                  rows="6"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">{{ $t('home.engineBadge') }}</div>
              </div>
            </div>

            <!-- 引擎设置：思考深度（部署级，全队共用） -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">&gt;_ 03 / {{ $t('home.engineSettings') }}</span>
              </div>
              <div class="think-level">
                <span class="tl-label">{{ $t('home.thinkLevelLabel') }}</span>
                <div class="tl-seg">
                  <button
                    class="tl-opt"
                    :class="{ active: thinkLevel === 'economy', eco: thinkLevel === 'economy' }"
                    @click="setThinkLevel('economy')"
                  >⚡ {{ $t('home.thinkLevelEconomy') }}</button>
                  <button
                    class="tl-opt"
                    :class="{ active: thinkLevel === 'deep' }"
                    @click="setThinkLevel('deep')"
                  >🧠 {{ $t('home.thinkLevelDeep') }}</button>
                </div>
                <span class="tl-hint">{{ thinkLevel === 'economy' ? $t('home.thinkLevelEconomyHint') : $t('home.thinkLevelDeepHint') }}</span>
                <span v-if="thinkLevelSaved" class="tl-saved">✓ {{ $t('home.thinkLevelSaved') }}</span>
              </div>
              <!-- 实时图谱开关（关闭可省 Zep 读取额度；不影响报告质量） -->
              <div class="think-level" style="margin-top:8px;">
                <span class="tl-label">{{ $t('home.graphVizLabel') }}</span>
                <div class="tl-seg">
                  <button class="tl-opt" :class="{ active: graphVizEnabled }" @click="setGraphViz(true)">📊 {{ $t('home.graphVizOn') }}</button>
                  <button class="tl-opt" :class="{ active: !graphVizEnabled }" @click="setGraphViz(false)">🚫 {{ $t('home.graphVizOff') }}</button>
                </div>
                <span class="tl-hint">{{ $t('home.graphVizHint') }}</span>
                <span v-if="graphVizSaved" class="tl-saved">✓ {{ $t('home.thinkLevelSaved') }}</span>
              </div>
              <!-- 报告采访开关（默认关闭）：报告生成期间与 Agent 实时对话，报告更有现场感但更耗 token -->
              <div class="think-level" style="margin-top:8px;">
                <span class="tl-label">{{ $t('home.interviewsLabel') }}</span>
                <div class="tl-seg">
                  <button class="tl-opt" :class="{ active: !interviewsEnabled }" @click="setInterviews(false)">🚫 {{ $t('home.interviewsOff') }}</button>
                  <button class="tl-opt" :class="{ active: interviewsEnabled }" @click="setInterviews(true)">🎤 {{ $t('home.interviewsOn') }}</button>
                </div>
                <span class="tl-hint">{{ $t('home.interviewsHint') }}</span>
                <span v-if="interviewsSaved" class="tl-saved">✓ {{ $t('home.thinkLevelSaved') }}</span>
              </div>
              <!-- 模型切换（部署级，全队共用）：MiniMax M3 / DeepSeek V4 Pro -->
              <div class="think-level" style="margin-top:8px;">
                <span class="tl-label">{{ $t('home.modelLabel') }}</span>
                <div class="tl-seg">
                  <button class="tl-opt" :class="{ active: activeModel === 'minimax-m3' }" @click="setModel('minimax-m3')">MiniMax M3</button>
                  <button class="tl-opt" :class="{ active: activeModel === 'deepseek-v4-pro' }" :disabled="!deepseekAvailable" @click="setModel('deepseek-v4-pro')">DeepSeek V4 Pro</button>
                </div>
                <span v-if="!deepseekAvailable" class="tl-hint">{{ $t('home.modelDeepseekUnavailable') }}</span>
                <span v-if="modelSaved" class="tl-saved">✓ {{ $t('home.thinkLevelSaved') }}</span>
              </div>
            </div>

            <!-- 启动按钮：手动逐步 / 自动直达报告 -->
            <div class="console-section btn-section" :class="{ 'queue-full': atCapacity }">
              <div class="btn-row">
                <button
                  class="start-engine-btn"
                  @click="startSimulation"
                  :disabled="!canSubmit || loading || atCapacity || autoBusy"
                >
                  <span v-if="!loading">{{ $t('home.startEngine') }}</span>
                  <span v-else>{{ $t('home.initializing') }}</span>
                  <span class="btn-arrow">→</span>
                </button>
                <button
                  class="auto-run-btn"
                  @click="startAutoRun"
                  :disabled="!canSubmit || loading || atCapacity"
                >
                  <template v-if="atCapacity">
                    <span class="auto-main">{{ $t('home.queueFullBtn') }}</span>
                    <span class="auto-sub">{{ $t('home.queueFullSub') }}</span>
                  </template>
                  <template v-else-if="autoBusy">
                    <span class="auto-main">⚡ {{ $t('home.joinQueueBtn') }}</span>
                    <span class="auto-sub">{{ $t('home.joinQueueSub', { a: qCounts.active, q: qCounts.queued }) }}</span>
                  </template>
                  <template v-else>
                    <span class="auto-main">⚡ {{ $t('home.autoRunBtn') }}</span>
                    <span class="auto-sub">{{ $t('home.autoRunSubtitle') }}</span>
                  </template>
                </button>
              </div>
              <div class="btn-hint">
                <template v-if="autoBusy || atCapacity">
                  <span class="h"><b>{{ $t('home.startEngine') }}</b>{{ $t('home.manualHintBusy') }}</span>
                  <span class="h"><b>{{ $t('home.joinQueueBtn') }}</b>{{ $t('home.autoHintBusy') }}</span>
                </template>
                <template v-else>
                  <span class="h"><b>{{ $t('home.startEngine') }}</b>{{ $t('home.manualHint') }}</span>
                  <span class="h"><b>{{ $t('home.autoRunBtn') }}</b>{{ $t('home.autoHint') }}</span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 历史项目数据库 -->
      <HistoryDatabase />

      <!-- 任务已创建提示条 -->
      <Transition name="toast-fade">
        <div v-if="toastMsg" class="job-toast">✓ {{ toastMsg }}</div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import LanguageSwitcher from '../components/LanguageSwitcher.vue'
import { getSimulationHistory, getSystemStatus } from '../api/simulation'
import { selectPrompts, addHidden, PROMPT_CAP } from '../utils/promptHistory'
import { enableAutoPilot, disableAutoPilot } from '../utils/autoPilot'
import { getSettings, updateSettings } from '../api/settings'
import { pipelineStore, queueCounts } from '../store/pipelineQueue'
import { fileToB64 } from '../store/fileCodec'
import { readCollapsed, writeCollapsed } from '../utils/bannerPref'

const router = useRouter()

// 横幅折叠：读初始值时就定好（不在 onMounted 里改），避免先展开再收起的闪烁
const bannerCollapsed = ref(
  typeof localStorage !== 'undefined' ? readCollapsed(localStorage) : false
)
const toggleBanner = () => {
  bannerCollapsed.value = !bannerCollapsed.value
  if (typeof localStorage !== 'undefined') writeCollapsed(localStorage, bannerCollapsed.value)
}
// 脚本里用 t()（模板的 $t 不需要）——漏了这行会让 showToast(t(...)) 直接
// ReferenceError，提示条永远弹不出来
const { t } = useI18n()

// 表单数据
const formData = ref({
  simulationRequirement: ''
})

// ===== 历史提示词（快速复用）=====
// 数据来自现有 /api/simulation/history；隐藏偏好仅存本浏览器。
const PROMPT_HIDDEN_KEY = 'mirofish_hidden_prompts'

const loadHiddenPrompts = () => {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROMPT_HIDDEN_KEY))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const promptHistoryItems = ref([])
const hiddenPrompts = ref(loadHiddenPrompts())
const showPromptHistory = ref(false)

const promptHistory = computed(() => selectPrompts(promptHistoryItems.value, hiddenPrompts.value))

const saveHiddenPrompts = () => {
  try {
    localStorage.setItem(PROMPT_HIDDEN_KEY, JSON.stringify(hiddenPrompts.value))
  } catch {
    // 存储不可用时静默降级：隐藏仅在当前会话生效
  }
}

const usePrompt = (p) => {
  formData.value.simulationRequirement = p.text
  showPromptHistory.value = false
}

const hidePrompt = (p) => {
  hiddenPrompts.value = addHidden(hiddenPrompts.value, p.text)
  saveHiddenPrompts()
}

const clearAllPrompts = () => {
  for (const p of [...promptHistory.value]) {
    hiddenPrompts.value = addHidden(hiddenPrompts.value, p.text)
  }
  saveHiddenPrompts()
  showPromptHistory.value = false
}

onMounted(async () => {
  try {
    const res = await getSimulationHistory(50)
    promptHistoryItems.value = Array.isArray(res.data) ? res.data : []
  } catch {
    // 拉取失败则按钮不显示，不影响页面其他功能
  }
})

// ===== 思考深度（部署级设置，服务器持久化）=====
const thinkLevel = ref('economy')
const thinkLevelSaved = ref(false)
let savedTimer = null

const setThinkLevel = async (level) => {
  if (level === thinkLevel.value) return
  const previous = thinkLevel.value
  thinkLevel.value = level
  try {
    await updateSettings({ think_level: level })
    thinkLevelSaved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => { thinkLevelSaved.value = false }, 2000)
  } catch {
    thinkLevel.value = previous // 保存失败则回滚显示
  }
}

// 实时图谱开关（部署级）
const graphVizEnabled = ref(true)
const graphVizSaved = ref(false)
let vizSavedTimer = null

const setGraphViz = async (enabled) => {
  if (enabled === graphVizEnabled.value) return
  const previous = graphVizEnabled.value
  graphVizEnabled.value = enabled
  try {
    await updateSettings({ graph_viz_enabled: enabled })
    graphVizSaved.value = true
    clearTimeout(vizSavedTimer)
    vizSavedTimer = setTimeout(() => { graphVizSaved.value = false }, 2000)
  } catch {
    graphVizEnabled.value = previous
  }
}

// 报告采访开关（部署级，默认关闭）
const interviewsEnabled = ref(false)
const interviewsSaved = ref(false)
let interviewsSavedTimer = null

const setInterviews = async (enabled) => {
  if (enabled === interviewsEnabled.value) return
  const previous = interviewsEnabled.value
  interviewsEnabled.value = enabled
  try {
    await updateSettings({ interviews_enabled: enabled })
    interviewsSaved.value = true
    clearTimeout(interviewsSavedTimer)
    interviewsSavedTimer = setTimeout(() => { interviewsSaved.value = false }, 2000)
  } catch {
    interviewsEnabled.value = previous
  }
}

// 模型切换（部署级）：MiniMax M3 / DeepSeek V4 Pro
const activeModel = ref('minimax-m3')
const deepseekAvailable = ref(false)
const modelSaved = ref(false)
let modelSavedTimer = null

const setModel = async (m) => {
  if (m === activeModel.value) return
  if (m === 'deepseek-v4-pro' && !deepseekAvailable.value) return
  const previous = activeModel.value
  activeModel.value = m
  try {
    await updateSettings({ active_model: m })
    modelSaved.value = true
    clearTimeout(modelSavedTimer)
    modelSavedTimer = setTimeout(() => { modelSaved.value = false }, 2000)
  } catch {
    activeModel.value = previous
  }
}

onMounted(async () => {
  try {
    const res = await getSettings()
    if (res.data?.think_level) thinkLevel.value = res.data.think_level
    if (typeof res.data?.graph_viz_enabled === 'boolean') graphVizEnabled.value = res.data.graph_viz_enabled
    if (typeof res.data?.interviews_enabled === 'boolean') interviewsEnabled.value = res.data.interviews_enabled
    if (res.data?.active_model) activeModel.value = res.data.active_model
    deepseekAvailable.value = !!res.data?.deepseek_available
  } catch {
    // 读取失败保持默认显示，不影响页面其他功能
  }
})

// 队列容量：满时（1 运行 + 2 排队）禁用整个开始区，避免超载
// 前端 store 是同步权威闸门；/api/status 作为二级保险
const capacityFull = ref(false)
const atCapacity = computed(() => capacityFull.value || pipelineStore.capacityFull.value)
// 队列状态载体：有任务进行中/排队时，自动直达按钮变身「加入队列」，
// 启动引擎禁用（自动任务运行期间不可手动分步）
const qCounts = computed(() => queueCounts(pipelineStore.raw()))
const autoBusy = computed(() => qCounts.value.active > 0 || qCounts.value.queued > 0)
let capacityTimer = null
const refreshCapacity = async () => {
  try {
    const res = await getSystemStatus()
    capacityFull.value = !!((res.data || res).capacity_full)
  } catch {
    // 查询失败不禁用，保持可用
  }
}
onMounted(() => {
  refreshCapacity()
  capacityTimer = setInterval(refreshCapacity, 5000)
})
onUnmounted(() => {
  if (capacityTimer) { clearInterval(capacityTimer); capacityTimer = null }
})

// 文件列表
const files = ref([])

// 状态
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)

// 文件输入引用
const fileInput = ref(null)

// 计算属性:是否可以提交
const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== '' && files.value.length > 0
})

// 触发文件选择
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// 处理文件选择
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

// 处理拖拽相关
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  
  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// 添加文件
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt', 'docx'].includes(ext)
  })
  files.value.push(...validFiles)
}

// 移除文件
const removeFile = (index) => {
  files.value.splice(index, 1)
}

// 滚动到底部
const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

let _tmpSeq = 0
// 点击即在历史列表插入一张「生成中」乐观卡片（自动+手动都插）。持久化到
// localStorage（base64 文件），刷新/切页都在。
const enqueueInstantCard = async (mode) => {
  const file = files.value[0]
  const enc = await fileToB64(file)
  const tmpId = `tmp_${Date.now()}_${_tmpSeq++}`
  const added = pipelineStore.add({
    _tmpId: tmpId,
    mode,
    prompt: formData.value.simulationRequirement,
    file,
    fileB64: enc.b64, fileName: enc.name, fileType: enc.type,
    createdAt: new Date().toISOString(),
    status: 'queued',
    projectId: null, buildTaskId: null, graphId: null, realSimId: null,
  })
  return added ? tmpId : null
}

// 任务入列后清空 01 的文件选择（提示词保留，常需复用）。
// 注意：绝不能在 launch() 之前清——launch 在异步 import 回调里才读取
// files.value 写入 pendingUpload，先清会让手动流程拿到空文件列表直接报错。
const clearUploadSelection = () => {
  files.value = []
  if (fileInput.value) fileInput.value.value = ''
}

// 轻量提示条（本页唯一用途，无需引入组件库）
const toastMsg = ref('')
let toastTimer = null
const showToast = (msg) => {
  toastMsg.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 2600)
}

// 开始模拟（手动）- 立即插卡 + 跳转，逐步由 Step 页面驱动
const startSimulation = async () => {
  if (!canSubmit.value || loading.value || pipelineStore.capacityFull.value) return
  loading.value = true                       // 防连点：b64 编码期间可重入
  try {
    disableAutoPilot()
    const id = await enqueueInstantCard('manual')
    if (!id) { showToast(t('home.queueFullHint')); return }
    launch()                                 // 手动仍进入分步流程（launch 已同步捕获文件）
    clearUploadSelection()
  } finally { loading.value = false }
}

// 自动直达报告 - 立即插卡，留在首页，由 app 级驱动器无人值守推进
const startAutoRun = async () => {
  if (!canSubmit.value || loading.value || pipelineStore.capacityFull.value) return
  loading.value = true                       // 防连点：b64 编码期间可重入
  try {
    // app 级驱动器负责推进整条流水线；不再设置旧的自动驾驶标记——否则用户点进
    // 步骤页时页面也会自动推进，与驱动器重复触发（双跑 = OOM）。标记关闭后步骤页
    // 只读展示，可安全点进查看进度。
    disableAutoPilot()
    if (files.value.length > 1) showToast(t('home.autoSingleFileHint'))
    const id = await enqueueInstantCard('auto')  // 不跳转：留在首页可继续排队
    if (!id) { showToast(t('home.queueFullHint')); return }
    clearUploadSelection()
    showToast(t('home.jobCreated'))
  } finally { loading.value = false }
}

const launch = () => {
  // 同步捕获再进异步回调：回调执行时 files.value 可能已被清空
  //（提交后会清空 01 的文件选择），不捕获会把空列表写进 pendingUpload。
  const capturedFiles = files.value
  const capturedRequirement = formData.value.simulationRequirement
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(capturedFiles, capturedRequirement)

    // 立即跳转到Process页面（使用特殊标识表示新建项目）
    router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
  })
}
</script>

<style scoped>
/* 全局变量与重置 */
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF4500;
  --gray-light: #F5F5F5;
  --gray-text: #666666;
  --border: #E5E5E5;
  /* 
    使用 Space Grotesk 作为主要标题字体，JetBrains Mono 作为代码/标签字体
    确保已在 index.html 引入这些 Google Fonts 
  */
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  --font-cn: 'Noto Sans SC', system-ui, sans-serif;
}

.home-container {
  min-height: 100vh;
  background: var(--white);
  font-family: var(--font-sans);
  color: var(--black);
}

/* 顶部导航 */
.navbar {
  height: 60px;
  background: var(--black);
  color: var(--white);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 1.2rem;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 16px;
}

.github-link {
  color: var(--white);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.github-link:hover {
  opacity: 0.8;
}

.arrow {
  font-family: sans-serif;
}

/* 主要内容区 */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 60px 40px;
}

/* Hero 区域 */
.hero-section {
  display: flex;
  justify-content: space-between;
  margin-bottom: 80px;
  position: relative;
}

/* 折叠横幅：细条 + 收起/展开按钮 */
.hero-collapsed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0 14px;
  margin-bottom: 32px;
  border-bottom: 1px solid #E5E7EB;
}

.banner-toggle {
  background: none;
  border: 1px solid #D1D5DB;
  border-radius: 2px;
  color: #6B7280;
  font-family: inherit;
  font-size: 11px;
  letter-spacing: 0.5px;
  padding: 5px 10px;
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
}

.banner-toggle:hover {
  color: #111827;
  border-color: #9CA3AF;
}

.banner-toggle-float {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 5;
}

.banner-toggle .chev {
  display: inline-block;
  margin-left: 2px;
}

.hero-left {
  flex: 1;
  padding-right: 60px;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 25px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.orange-tag {
  background: var(--orange);
  color: var(--white);
  padding: 4px 10px;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 0.75rem;
}

.version-text {
  color: #999;
  font-weight: 500;
  letter-spacing: 0.5px;
}

.main-title {
  font-size: 4.5rem;
  line-height: 1.2;
  font-weight: 500;
  margin: 0 0 40px 0;
  letter-spacing: -2px;
  color: var(--black);
}

.gradient-text {
  background: linear-gradient(90deg, #000000 0%, #444444 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

.hero-desc {
  font-size: 1.05rem;
  line-height: 1.8;
  color: var(--gray-text);
  max-width: 640px;
  margin-bottom: 50px;
  font-weight: 400;
  text-align: justify;
}

.hero-desc p {
  margin-bottom: 1.5rem;
}

.highlight-bold {
  color: var(--black);
  font-weight: 700;
}

.highlight-orange {
  color: var(--orange);
  font-weight: 700;
  font-family: var(--font-mono);
}

.highlight-code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: var(--black);
  font-weight: 600;
}

.slogan-text {
  font-size: 1.2rem;
  font-weight: 520;
  color: var(--black);
  letter-spacing: 1px;
  border-left: 3px solid var(--orange);
  padding-left: 15px;
  margin-top: 20px;
}

.blinking-cursor {
  color: var(--orange);
  animation: blink 1s step-end infinite;
  font-weight: 700;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.decoration-square {
  width: 16px;
  height: 16px;
  background: var(--orange);
}

.hero-right {
  flex: 0.8;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
}

.logo-container {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  padding-right: 40px;
}

.hero-logo {
  max-width: 500px; /* 调整logo大小 */
  width: 100%;
}

.scroll-down-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--orange);
  font-size: 1.2rem;
  transition: all 0.2s;
}

.scroll-down-btn:hover {
  border-color: var(--orange);
}

/* Dashboard 双栏布局 */
.dashboard-section {
  display: flex;
  gap: 60px;
  border-top: 1px solid var(--border);
  padding-top: 60px;
  align-items: flex-start;
}

.dashboard-section .left-panel,
.dashboard-section .right-panel {
  display: flex;
  flex-direction: column;
}

/* 左侧面板 */
.left-panel {
  flex: 0.8;
}

.panel-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}

.status-dot {
  color: var(--orange);
  font-size: 0.8rem;
}

.section-title {
  font-size: 2rem;
  font-weight: 520;
  margin: 0 0 15px 0;
}

.section-desc {
  color: var(--gray-text);
  margin-bottom: 25px;
  line-height: 1.6;
}

.metrics-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.metric-card {
  border: 1px solid var(--border);
  padding: 20px 30px;
  min-width: 150px;
}

.metric-value {
  font-family: var(--font-mono);
  font-size: 1.8rem;
  font-weight: 520;
  margin-bottom: 5px;
}

.metric-label {
  font-size: 0.85rem;
  color: #999;
}

/* 项目模拟步骤介绍 */
.steps-container {
  border: 1px solid var(--border);
  padding: 30px;
  position: relative;
}

.steps-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  margin-bottom: 25px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.diamond-icon {
  font-size: 1.2rem;
  line-height: 1;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workflow-item {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.step-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--black);
  opacity: 0.3;
}

.step-info {
  flex: 1;
}

.step-title {
  font-weight: 520;
  font-size: 1rem;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 0.85rem;
  color: var(--gray-text);
}

/* 右侧交互控制台 */
.right-panel {
  flex: 1.2;
}

.console-box {
  border: 1px solid #CCC; /* 外部实线 */
  padding: 8px; /* 内边距形成双重边框感 */
}

.console-section {
  padding: 20px;
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #666;
}

.upload-zone {
  border: 1px dashed #CCC;
  height: 200px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #FAFAFA;
}

.upload-zone.has-files {
  align-items: flex-start;
}

.upload-zone:hover {
  background: #F0F0F0;
  border-color: #999;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 40px;
  height: 40px;
  border: 1px solid #DDD;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 15px;
  color: #999;
}

.upload-title {
  font-weight: 500;
  font-size: 0.9rem;
  margin-bottom: 5px;
}

.upload-hint {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #999;
}

.file-list {
  width: 100%;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-item {
  display: flex;
  align-items: center;
  background: var(--white);
  padding: 8px 12px;
  border: 1px solid #EEE;
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.file-name {
  flex: 1;
  margin: 0 10px;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
  color: #999;
}

.console-divider {
  display: flex;
  align-items: center;
  margin: 10px 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #EEE;
}

.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #BBB;
  letter-spacing: 1px;
}

.input-wrapper {
  position: relative;
  border: 1px solid #DDD;
  background: #FAFAFA;
}

.code-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 20px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  min-height: 150px;
}

.model-badge {
  position: absolute;
  bottom: 10px;
  right: 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #AAA;
}

.start-engine-btn {
  width: 100%;
  background: var(--black);
  color: var(--white);
  border: none;
  padding: 20px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  letter-spacing: 1px;
  position: relative;
  overflow: hidden;
}

/* 可点击状态（非禁用） */
.start-engine-btn:not(:disabled) {
  background: var(--black);
  border: 1px solid var(--black);
  animation: pulse-border 2s infinite;
}

.start-engine-btn:hover:not(:disabled) {
  background: var(--orange);
  border-color: var(--orange);
  transform: translateY(-2px);
}

.start-engine-btn:active:not(:disabled) {
  transform: translateY(0);
}

.start-engine-btn:disabled {
  background: #E5E5E5;
  color: #999;
  cursor: not-allowed;
  transform: none;
  border: 1px solid #E5E5E5;
}

/* 自动直达报告：与启动引擎并排的第二启动按钮 */
.btn-row { display: flex; gap: 12px; }
.btn-row .start-engine-btn { flex: 1; width: auto; }
.auto-run-btn {
  flex: 1;
  border: none;
  padding: 12px 16px;
  color: var(--white);
  background: linear-gradient(135deg, #FF5722, #FF8A50);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  transition: all 0.3s ease;
}
.auto-run-btn .auto-main {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1rem;
  letter-spacing: 1px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.auto-run-btn .auto-sub {
  font-size: 0.68rem;
  font-weight: 500;
  opacity: 0.92;
  letter-spacing: 0.02em;
}
.auto-run-btn:hover:not(:disabled) { filter: brightness(1.07); transform: translateY(-2px); }
.auto-run-btn:active:not(:disabled) { transform: translateY(0); }
.auto-run-btn:disabled {
  background: #E5E5E5;
  color: #999;
  cursor: not-allowed;
  transform: none;
}
/* 任务已创建提示条 */
.job-toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  z-index: 9999;
  background: #111827;
  color: #fff;
  font-size: 0.82rem;
  letter-spacing: 0.5px;
  padding: 10px 18px;
  border-radius: 4px;
  box-shadow: 0 8px 20px -6px rgba(0,0,0,.35);
  font-family: inherit;
}
.toast-fade-enter-active, .toast-fade-leave-active { transition: opacity .25s ease, transform .25s ease; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* 队列已满：整个开始区变暗 + 提示 */
.btn-section.queue-full { opacity: 0.7; }
.queue-full-hint {
  margin-top: 10px;
  padding: 8px 12px;
  font-size: 0.72rem;
  color: #D97706;
  background: #FEF7EC;
  border: 1px solid #F5C77E;
  text-align: center;
  letter-spacing: 0.5px;
}

.btn-hint {
  display: flex;
  gap: 12px; /* 与按钮行对齐 */
  margin-top: 10px;
  font-size: 0.72rem;
  color: #999;
  line-height: 1.6;
}

/* 思考深度（引擎设置） */
.think-level {
  display: flex; align-items: center; gap: 10px; margin-top: 10px;
  padding: 12px 14px; border: 1px solid #F3F4F6; border-radius: 10px;
  background: #FCFCFB;
}
.tl-label {
  font-family: var(--font-mono); font-size: 11.5px; font-weight: 700;
  color: #444; white-space: nowrap;
}
.tl-seg { display: flex; background: #EFEFEC; border-radius: 8px; padding: 3px; gap: 3px; }
.tl-opt {
  border: 0; border-radius: 6px; padding: 7px 16px; font-size: 12px;
  font-weight: 600; color: #666; background: transparent; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 6px;
  white-space: nowrap; font-family: inherit;
  min-width: 88px;  /* 两行开关按钮宽度一致 */
}
.tl-opt.active { background: #fff; color: #000; box-shadow: 0 1px 4px rgba(0,0,0,.10); }
.tl-opt.active.eco { color: #C2410C; }
.tl-hint { font-size: 11px; color: #999; line-height: 1.5; flex: 1; }
.tl-saved {
  font-family: var(--font-mono); font-size: 10px; color: #1A936F;
  white-space: nowrap;
}
.btn-hint .h { flex: 1; }
/* 右列按钮内容居中，其提示也居中，使两列各自上下对齐 */
.btn-hint .h:last-child { text-align: center; }
.btn-hint b { color: #555; font-weight: 600; }

/* 引导动画：微妙的边框脉冲 */
@keyframes pulse-border {
  0% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(0, 0, 0, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0); }
}

/* 响应式适配 */
@media (max-width: 1024px) {
  .dashboard-section {
    flex-direction: column;
  }
  
  .hero-section {
    flex-direction: column;
  }
  
  .hero-left {
    padding-right: 0;
    margin-bottom: 40px;
  }
  
  .hero-logo {
    max-width: 200px;
    margin-bottom: 20px;
  }
}
</style>

<style>
/* English locale adjustments (unscoped to target html[lang]) */
html[lang="en"] .main-title {
  font-size: 3.5rem;
  font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  letter-spacing: -1px;
}

html[lang="en"] .hero-desc {
  text-align: left;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  letter-spacing: 0;
}

html[lang="en"] .slogan-text {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  letter-spacing: 0;
}

html[lang="en"] .tag-row {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

html[lang="en"] .navbar .nav-links {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* Left pane: system status + workflow */
html[lang="en"] .status-section {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

html[lang="en"] .status-section .status-ready {
  font-size: 1.6rem;
}

html[lang="en"] .status-section .metric-value {
  font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 1.4rem;
}

html[lang="en"] .workflow-list .step-title {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

html[lang="en"] .workflow-list .step-desc {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
  font-size: 0.72rem !important;
  line-height: 1.4 !important;
}

html[lang="en"] .workflow-list {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ── 历史提示词（快速复用） ─────────────────────────── */
.prompt-history-btn {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid #E5E7EB; background: #fff; border-radius: 7px;
  padding: 5px 10px; font-size: 11.5px; font-weight: 600; color: #444;
  cursor: pointer; font-family: inherit;
}
.prompt-history-btn:hover { border-color: #bbb; }
.prompt-history-btn .ph-ic { font-size: 12px; }
.prompt-history-backdrop { position: fixed; inset: 0; z-index: 30; }
.prompt-history-panel {
  position: absolute; top: 0; left: 0; right: 0; z-index: 31;
  background: #fff; border: 1px solid #E5E7EB; border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,.14); overflow: hidden;
}
.php-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid #F3F4F6;
}
.php-title {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  font-weight: 700; letter-spacing: .05em; color: #666;
}
.php-actions { display: flex; align-items: center; gap: 12px; }
.php-clear {
  border: 0; background: none; font-size: 11px; font-weight: 600;
  color: #999; cursor: pointer; text-decoration: underline; font-family: inherit;
}
.php-clear:hover { color: #C2283B; }
.php-close { border: 0; background: none; font-size: 13px; color: #999; cursor: pointer; }
.php-list { max-height: 300px; overflow-y: auto; }
.php-item {
  padding: 11px 14px; border-bottom: 1px solid #F3F4F6;
  cursor: pointer; position: relative;
}
.php-item:hover { background: #FAFAFA; }
.php-item:last-child { border-bottom: none; }
.php-text {
  font-size: 12.5px; line-height: 1.55; color: #222; padding-right: 22px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.php-meta {
  font-family: 'JetBrains Mono', monospace; font-size: 10px;
  color: #999; margin-top: 5px;
}
.php-remove {
  position: absolute; top: 9px; right: 10px; border: 0; background: none;
  color: #ccc; font-size: 13px; cursor: pointer; line-height: 1; display: none;
}
.php-item:hover .php-remove { display: block; }
.php-remove:hover { color: #C2283B; }
.php-foot {
  padding: 8px 14px; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  color: #999; border-top: 1px solid #F3F4F6; text-align: center;
}
</style>
