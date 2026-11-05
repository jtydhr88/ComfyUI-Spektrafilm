import type { ComfyApi, ComfyApp, ComfyExtension, DOMWidget, DOMWidgetOptions } from '@comfyorg/comfyui-frontend-types'

// @ts-ignore - served by ComfyUI at runtime
import { app as rawApp } from '../../../scripts/app.js'
// @ts-ignore - served by ComfyUI at runtime
import { api as rawApi } from '../../../scripts/api.js'

export const app = rawApp as ComfyApp
export const api = rawApi as ComfyApi

type LGraphNode = Parameters<NonNullable<ComfyExtension['nodeCreated']>>[0]
export type Widget = NonNullable<LGraphNode['widgets']>[number]

export interface ComfyNode extends LGraphNode {
  comfyClass: string
  onExecuted?: (output: Record<string, unknown>) => void
  addDOMWidget<T extends HTMLElement>(name: string, type: string, element: T, options?: DOMWidgetOptions<string>): DOMWidget<T, string>
}

export const PARAMS_TYPE = 'SPEKTRAFILM_PARAMS'
export const SIMULATION_NODE = 'SpektrafilmFilmSimulation'

export function chain<A extends unknown[]>(original: ((...args: A) => void) | undefined, extra: (...args: A) => void) {
  return function (this: unknown, ...args: A) {
    original?.apply(this, args)
    extra.apply(this, args)
  }
}
