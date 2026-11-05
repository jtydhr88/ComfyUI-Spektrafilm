import { app } from '@/comfy'

const messages = {
  en: {
    upload: 'choose file to upload',
    uploadFailed: 'Upload failed',
    live: 'live preview',
    full: 'grain & blur',
    waiting: 'Run the workflow once; the live preview then reuses that input image while you adjust the nodes.',
    result: 'run result',
    unlinked: 'Connect this to the output of Spektrafilm Film Simulation.',
    error: 'Preview failed'
  },
  zh: {
    upload: '选择文件上传',
    uploadFailed: '上传失败',
    live: '实时预览',
    full: '颗粒和模糊',
    waiting: '先运行一次工作流，之后调节点时，实时预览会复用这次的输入图。',
    result: '运行结果',
    unlinked: '把它接到 Spektrafilm Film Simulation 的输出上。',
    error: '预览失败'
  }
}

export type MessageKey = keyof typeof messages.en

export function t(key: MessageKey): string {
  const locale = String(app.extensionManager.setting.get('Comfy.Locale') ?? 'en')
  return (locale.startsWith('zh') ? messages.zh : messages.en)[key]
}
