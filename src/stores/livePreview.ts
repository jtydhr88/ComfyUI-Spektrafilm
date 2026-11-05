import { defineStore } from 'pinia'
import { markRaw, reactive } from 'vue'

import { api, app, type ComfyNode } from '@/comfy'
import { composeRequest, simulationSource } from '@/graph'
import type { LiveImage, LiveLut } from '@/lutRenderer'

const DEBOUNCE_MS = 60

export type LiveStatus = 'unlinked' | 'waiting' | 'loading' | 'live' | 'result' | 'error'

export interface LiveEntry {
  enabled: boolean
  fast: boolean
  status: LiveStatus
  message: string
  view: 'image' | 'lut'
  url: string
  count: number
  image: LiveImage | null
  lut: LiveLut | null
  signature: string
  busy: boolean
  again: boolean
}

export interface SavedImage {
  filename: string
  subfolder: string
  type: string
}

class PreviewError extends Error {}

async function fetchOk(path: string, init?: RequestInit): Promise<Response | null> {
  const response = await api.fetchApi(path, init)
  if (response.status === 404) return null
  if (!response.ok) throw new PreviewError((await response.json()).error ?? response.statusText)
  return response
}

export const useLivePreviewStore = defineStore('spektrafilmLivePreview', () => {
  const entries = reactive<Record<string, LiveEntry>>({})
  const previews = new Map<string, ComfyNode>()
  const inputKeys = new WeakMap<ComfyNode, string>()
  const images = new Map<string, Promise<LiveImage | null>>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let nextId = 0

  function register(preview: ComfyNode): string {
    const id = String(nextId++)
    previews.set(id, markRaw(preview))
    entries[id] = {
      enabled: true, fast: true, status: 'waiting', message: '', view: 'image', url: '', count: 0,
      image: null, lut: null, signature: '', busy: false, again: false
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

  function inputKey(simulation: ComfyNode): string | undefined {
    return inputKeys.get(simulation) ?? (simulation.graph === app.rootGraph ? `${app.rootGraph.id}:${simulation.id}` : undefined)
  }

  function request(id: string): string | null | undefined {
    const preview = previews.get(id)
    const simulation = preview && simulationSource(preview)
    const entry = entries[id]
    if (!simulation || !entry) return null
    const key = inputKey(simulation)
    return key && JSON.stringify(composeRequest(simulation, key, entry.fast))
  }

  function simulationExecuted(simulation: ComfyNode, key: string) {
    inputKeys.set(markRaw(simulation), key)
    images.delete(key)
  }

  function previewExecuted(id: string, saved: SavedImage[]) {
    const entry = entries[id]
    if (!entry || !saved.length) return
    const { filename, subfolder, type } = saved[0]
    setUrl(entry, api.apiURL(`/view?${new URLSearchParams({ filename, subfolder, type })}`))
    entry.view = 'image'
    entry.count = saved.length
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

  function loadImage(key: string): Promise<LiveImage | null> {
    let image = images.get(key)
    if (!image) {
      image = fetchOk(`/spektrafilm/live_input?${new URLSearchParams({ key })}`).then(async (response) => response && markRaw({
        width: Number(response.headers.get('X-Width')),
        height: Number(response.headers.get('X-Height')),
        data: new Uint16Array(await response.arrayBuffer())
      }))
      image.catch(() => images.delete(key))
      images.set(key, image)
    }
    return image
  }

  async function renderLut(entry: LiveEntry, body: string): Promise<boolean> {
    const { key } = JSON.parse(body) as { key: string }
    const [image, response] = await Promise.all([
      loadImage(key),
      fetchOk('/spektrafilm/live_lut', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
    ])
    if (!image || !response) return false
    entry.image = image
    entry.lut = markRaw({
      size: Number(response.headers.get('X-Lut-Size')),
      max: Number(response.headers.get('X-Lut-Max')),
      gamma: Number(response.headers.get('X-Lut-Gamma')),
      data: new Uint16Array(await response.arrayBuffer())
    })
    entry.view = 'lut'
    return true
  }

  async function renderImage(entry: LiveEntry, body: string): Promise<boolean> {
    const response = await fetchOk('/spektrafilm/live_preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
    if (!response) return false
    setUrl(entry, URL.createObjectURL(await response.blob()))
    entry.view = 'image'
    return true
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
      const rendered = entry.fast ? await renderLut(entry, body) : await renderImage(entry, body)
      if (!rendered) {
        entry.status = 'waiting'
        return
      }
      entry.signature = body
      entry.count = 1
      entry.status = 'live'
    } catch (error) {
      entry.signature = body
      entry.status = 'error'
      entry.message = error instanceof PreviewError ? error.message : String(error)
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
