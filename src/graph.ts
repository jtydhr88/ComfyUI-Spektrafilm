import { PARAMS_TYPE, type ComfyNode } from '@/comfy'

const BYPASS = 4
const SKIPPED_WIDGETS = new Set(['control_after_generate'])

export interface LiveRequest {
  key: string
  fast: boolean
  main: Record<string, unknown>
  chain: { type: string; inputs: Record<string, unknown> }[]
}

function widgetValues(node: ComfyNode): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const widget of node.widgets ?? []) {
    if (widget.serialize === false || widget.type === 'button' || SKIPPED_WIDGETS.has(widget.name)) continue
    values[widget.name] = widget.value
  }
  return values
}

function paramsSource(node: ComfyNode): ComfyNode | null {
  const slot = node.findInputSlot('params')
  if (slot < 0) return null
  const source = node.getInputNode(slot) as ComfyNode | null
  return source?.outputs?.[0]?.type === PARAMS_TYPE ? source : null
}

export function composeRequest(node: ComfyNode, key: string, fast: boolean): LiveRequest {
  const chain: LiveRequest['chain'] = []
  for (let source = paramsSource(node); source; source = paramsSource(source)) {
    if (source.mode !== BYPASS) chain.unshift({ type: source.comfyClass, inputs: widgetValues(source) })
  }
  return { key, fast, main: widgetValues(node), chain }
}
