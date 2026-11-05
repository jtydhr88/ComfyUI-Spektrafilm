import { createPinia } from 'pinia'
import { createApp } from 'vue'

import LivePreview from '@/components/LivePreview.vue'
import { api, app, chain, SIMULATION_NODE, type ComfyNode } from '@/comfy'
import { useLivePreviewStore } from '@/stores/livePreview'
import { addUploadButton } from '@/upload'

const pinia = createPinia()
const store = useLivePreviewStore(pinia)

function addLivePreview(node: ComfyNode) {
  const container = document.createElement('div')
  container.style.cssText = 'width: 100%; height: 100%;'
  const widget = node.addDOMWidget('spektrafilm_live', 'spektrafilm_live', container, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 240
  })
  widget.serialize = false

  const id = store.register(node)
  const vueApp = createApp(LivePreview, { entryId: id })
  vueApp.use(pinia)
  vueApp.mount(container)

  node.onExecuted = chain(node.onExecuted, (output) => {
    const key = (output.spektrafilm_live as string[] | undefined)?.[0]
    if (key) store.executed(id, key)
  })
  node.onRemoved = chain(node.onRemoved, () => {
    vueApp.unmount()
    store.unregister(id)
  })
}

app.registerExtension({
  name: 'Spektrafilm',
  setup() {
    api.addEventListener('graphChanged', () => store.schedule())
  },
  nodeCreated(created) {
    const node = created as ComfyNode
    if (!node.comfyClass.startsWith('Spektrafilm')) return
    for (const widget of node.widgets ?? []) widget.callback = chain(widget.callback, () => store.schedule())
    node.onConnectionsChange = chain(node.onConnectionsChange, () => store.schedule())
    addUploadButton(node)
    if (node.comfyClass === SIMULATION_NODE) addLivePreview(node)
  }
})
