import { api, app, type ComfyNode, type Widget } from '@/comfy'
import { t } from '@/i18n'

const UPLOADS: Record<string, { widget: string; accept: string }> = {
  SpektrafilmLoadRaw: {
    widget: 'raw_file',
    accept: '.3fr,.ari,.arw,.bay,.cr2,.cr3,.crw,.dcr,.dng,.erf,.fff,.iiq,.k25,.kdc,.mef,.mos,.mrw,.nef,.nrw,.orf,.pef,.raf,.raw,.rw2,.rwl,.sr2,.srf,.srw,.x3f'
  },
  SpektrafilmLoadImage: {
    widget: 'image',
    accept: '.exr,.tif,.tiff,.png,.jpg,.jpeg,.hdr'
  }
}

async function upload(file: File, combo: Widget) {
  const body = new FormData()
  body.append('image', file)
  const response = await api.fetchApi('/upload/image', { method: 'POST', body })
  if (!response.ok) {
    app.extensionManager.toast.add({ severity: 'error', summary: t('uploadFailed'), detail: `${file.name}: ${response.status} ${response.statusText}`, life: 5000 })
    return
  }
  const data = await response.json()
  const name = data.subfolder ? `${data.subfolder}/${data.name}` : data.name
  const values = combo.options.values as string[]
  if (!values.includes(name)) values.push(name)
  combo.value = name
  combo.callback?.(name)
}

export function addUploadButton(node: ComfyNode) {
  const spec = UPLOADS[node.comfyClass]
  if (!spec) return
  const combo = node.widgets?.find((w) => w.name === spec.widget)
  if (!combo) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = spec.accept
  input.onchange = async () => {
    const file = input.files?.[0]
    if (file) await upload(file, combo)
    input.value = ''
  }
  const button = node.addWidget('button', t('upload'), '', () => input.click(), { serialize: false })
  button.serialize = false
}
