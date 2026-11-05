<script setup lang="ts">
import { computed } from 'vue'

import { t } from '@/i18n'
import { useLivePreviewStore } from '@/stores/livePreview'

const { entryId } = defineProps<{ entryId: string }>()

const store = useLivePreviewStore()
const entry = computed(() => store.entries[entryId])
</script>

<template>
  <div v-if="entry" class="sf-live">
    <div class="sf-live__bar">
      <button type="button" role="switch" :aria-checked="entry.enabled" class="sf-live__switch" @click="store.setOption(entryId, 'enabled', !entry.enabled)">
        <span class="sf-live__track"><span class="sf-live__thumb" /></span>
        {{ t('live') }}
      </button>
      <button type="button" role="switch" :aria-checked="!entry.fast" :disabled="!entry.enabled" class="sf-live__switch" @click="store.setOption(entryId, 'fast', !entry.fast)">
        <span class="sf-live__track"><span class="sf-live__thumb" /></span>
        {{ t('full') }}
      </button>
      <span v-if="entry.status === 'loading'" class="sf-live__spinner" />
    </div>
    <div class="sf-live__view">
      <img v-if="entry.url" :src="entry.url" :class="{ 'sf-live__img--stale': entry.status === 'loading' }" class="sf-live__img" />
      <span v-if="entry.url && (entry.status === 'live' || entry.status === 'result')" class="sf-live__badge">
        {{ entry.status === 'live' ? t('live') : t('result') }}<template v-if="entry.count > 1"> · 1/{{ entry.count }}</template>
      </span>
      <p v-if="entry.status === 'unlinked'" class="sf-live__note">{{ t('unlinked') }}</p>
      <p v-if="entry.status === 'waiting' && !entry.url" class="sf-live__note">{{ t('waiting') }}</p>
      <p v-if="entry.status === 'error'" class="sf-live__note sf-live__note--error">{{ t('error') }}: {{ entry.message }}</p>
    </div>
  </div>
</template>

<style scoped>
.sf-live {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  height: 100%;
  font-size: 12px;
  color: var(--input-text, #ddd);
}
.sf-live__bar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sf-live__switch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
  user-select: none;
}
.sf-live__switch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sf-live__track {
  display: inline-flex;
  align-items: center;
  width: 36px;
  height: 20px;
  padding: 0 2px;
  box-sizing: border-box;
  border-radius: 9999px;
  background: var(--border, #444);
  transition: background-color 0.15s;
}
.sf-live__thumb {
  width: 16px;
  height: 16px;
  border-radius: 9999px;
  background: var(--background, #fff);
  box-shadow: 0 1px 2px rgb(0 0 0 / 0.3);
  transition: transform 0.15s;
}
.sf-live__switch[aria-checked='true'] .sf-live__track {
  background: var(--primary, #3b82f6);
}
.sf-live__switch[aria-checked='true'] .sf-live__thumb {
  transform: translateX(14px);
}
.sf-live__spinner {
  width: 10px;
  height: 10px;
  margin-left: auto;
  border: 2px solid var(--descrip-text, #999);
  border-top-color: transparent;
  border-radius: 50%;
  animation: sf-spin 0.8s linear infinite;
}
.sf-live__view {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--comfy-input-bg, #222);
  overflow: hidden;
}
.sf-live__img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  transition: opacity 0.15s;
}
.sf-live__img--stale {
  opacity: 0.7;
}
.sf-live__badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  background: color-mix(in srgb, var(--comfy-input-bg, #222) 80%, transparent);
}
.sf-live__note {
  margin: 0;
  padding: 12px;
  text-align: center;
  color: var(--descrip-text, #999);
}
.sf-live__note--error {
  position: absolute;
  inset: auto 0 0 0;
  color: var(--error-text, #f87171);
  background: color-mix(in srgb, var(--comfy-input-bg, #222) 85%, transparent);
}
@keyframes sf-spin {
  to { transform: rotate(360deg); }
}
</style>
