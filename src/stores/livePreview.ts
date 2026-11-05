import { defineStore } from 'pinia'
import { markRaw, reactive } from 'vue'

import { api, app, type ComfyNode } from '@/comfy'
import { composeRequest, simulationSource } from '@/graph'

const DEBOUNCE_MS = 120

export type LiveStatus = 'unlinked' | 'waiting' | 'loading' | 'live' | 'result' | 'error'

export interface LiveEntry {
  enabled: boolean
  fast: boolean
  status: LiveStatus
  message: string
  url: string
  count: number
  signature: string
  busy: boolean
  again: boolean
}

export interface SavedImage {
  filename: string
  subfolder: string
  type: string
}

export const useLivePreviewStore = defineStore('spektrafilmLivePreview', () => {
  const entries = reactive<Record<string, LiveEntry>>({})
  const previews = new Map<string, ComfyNode>()
  const inputKeys = new WeakMap<ComfyNode, string>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let nextId = 0

  function register(preview: ComfyNode): string {
    const id = String(nextId++)
    previews.set(id, markRaw(preview))
    entries[id] = {
      enabled: true, fast: true, status: 'waiting', message: '', url: '', count: 0,
      signature: '', busy: false, again: false
    }
    schedule()
    return id
  }

  function setUrl(entry: LiveEntry, url: string) {
    if (entry.url.startsWith('blob:')) URL.revokeObjectURL(entry.url)
    entry.url = url
  }

  function unregister(id: string) {
    const entry = entries[id]
    if (entry) setUrl(entry, '')
    delete entries[id]
    previews.delete(id)
  }

  function request(id: string): string | null | undefined {
    const preview = previews.get(id)
    const simulation = preview && simulationSource(preview)
    const entry = entries[id]
    if (!simulation || !entry) return null
    const key = inputKeys.get(simulation) ?? (simulation.graph === app.rootGraph ? `${app.rootGraph.id}:${simulation.id}` : undefined)
    return key && JSON.stringify(composeRequest(simulation, key, entry.fast))
  }

  function simulationExecuted(simulation: ComfyNode, key: string) {
    inputKeys.set(markRaw(simulation), key)
  }

  function previewExecuted(id: string, images: SavedImage[]) {
    const entry = entries[id]
    if (!entry || !images.length) return
    const { filename, subfolder, type } = images[0]
    setUrl(entry, api.apiURL(`/view?${new URLSearchParams({ filename, subfolder, type })}`))
    entry.count = images.length
    entry.status = 'result'
    entry.signature = request(id) ?? ''
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
      for (const id of previews.keys()) void refresh(id)
    }, DEBOUNCE_MS)
  }

  async function refresh(id: string) {
    const entry = entries[id]
    if (!entry?.enabled) return
    const body = request(id)
    if (!body) {
      entry.status = body === null ? 'unlinked' : 'waiting'
      entry.signature = ''
      return
    }
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
      setUrl(entry, URL.createObjectURL(await response.blob()))
      entry.count = 1
      entry.status = 'live'
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

  return { entries, register, unregister, simulationExecuted, previewExecuted, setOption, schedule }
})
