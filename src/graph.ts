import { PARAMS_TYPE, SIMULATION_NODE, type ComfyNode } from '@/comfy'

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

function source(node: ComfyNode, input: string): ComfyNode | null {
  const slot = node.findInputSlot(input)
  return slot < 0 ? null : (node.getInputNode(slot) as ComfyNode | null)
}

function paramsSource(node: ComfyNode): ComfyNode | null {
  const params = source(node, 'params')
  return params?.outputs?.[0]?.type === PARAMS_TYPE ? params : null
}

export function simulationSource(preview: ComfyNode): ComfyNode | null {
  const simulation = source(preview, 'images')
  return simulation?.comfyClass === SIMULATION_NODE && simulation.mode !== BYPASS ? simulation : null
}

export function composeRequest(simulation: ComfyNode, key: string, fast: boolean): LiveRequest {
  const chain: LiveRequest['chain'] = []
  for (let params = paramsSource(simulation); params; params = paramsSource(params)) {
    if (params.mode !== BYPASS) chain.unshift({ type: params.comfyClass, inputs: widgetValues(params) })
  }
  return { key, fast, main: widgetValues(simulation), chain }
}
