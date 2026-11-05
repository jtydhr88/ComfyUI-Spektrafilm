import { defineStore } from 'pinia'
import { markRaw, reactive } from 'vue'

import { api, type ComfyNode } from '@/comfy'
import { composeRequest } from '@/graph'

const DEBOUNCE_MS = 120

export type LiveStatus = 'waiting' | 'loading' | 'ready' | 'error'

export interface LiveEntry {
  key: string
  enabled: boolean
  fast: boolean
  status: LiveStatus
  message: string
  url: string
  signature: string
  busy: boolean
  again: boolean
}

export const useLivePreviewStore = defineStore('spektrafilmLivePreview', () => {
  const entries = reactive<Record<string, LiveEntry>>({})
  const nodes = new Map<string, ComfyNode>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let nextId = 0

  function register(node: ComfyNode): string {
    const id = String(nextId++)
    nodes.set(id, markRaw(node))
    entries[id] = {
      key: '', enabled: true, fast: true, status: 'waiting',
      message: '', url: '', signature: '', busy: false, again: false
    }
    schedule()
    return id
  }

  function unregister(id: string) {
    const entry = entries[id]
    if (entry?.url) URL.revokeObjectURL(entry.url)
    delete entries[id]
    nodes.delete(id)
  }

  function executed(id: string, key: string) {
    const entry = entries[id]
    if (!entry) return
    entry.key = key
    entry.signature = ''
    schedule()
  }

  function setOption(id: string, option: 'enabled' | 'fast', value: boolean) {
    const entry = entries[id]
    if (!entry) return
    entry[option] = value
    schedule()
  }

  function schedule() {
    clearTimeout(timer)
    timer = setTimeout(() => {
      for (const id of nodes.keys()) void refresh(id)
    }, DEBOUNCE_MS)
  }

  async function refresh(id: string) {
    const node = nodes.get(id)
    const entry = entries[id]
    if (!node || !entry?.enabled) return
    const body = JSON.stringify(composeRequest(node, entry.key || String(node.id), entry.fast))
    if (body === entry.signature) return
    if (entry.busy) {
      entry.again = true
      return
    }
    entry.busy = true
    entry.status = 'loading'
    try {
      const response = await api.fetchApi('/spektrafilm/live_preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body
      })
      if (response.status === 404) {
        entry.status = 'waiting'
        return
      }
      entry.signature = body
      if (!response.ok) {
        entry.status = 'error'
        entry.message = (await response.json()).error ?? response.statusText
        return
      }
      if (entry.url) URL.revokeObjectURL(entry.url)
      entry.url = URL.createObjectURL(await response.blob())
      entry.status = 'ready'
    } catch (error) {
      entry.status = 'error'
      entry.message = String(error)
    } finally {
      entry.busy = false
      if (entry.again && entries[id]) {
        entry.again = false
        void refresh(id)
      }
    }
  }

  return { entries, register, unregister, executed, setOption, schedule }
})
