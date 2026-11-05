import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const UPLOADS = {
  SpektrafilmLoadRaw: {
    widget: "raw_file",
    accept: ".3fr,.ari,.arw,.bay,.cr2,.cr3,.crw,.dcr,.dng,.erf,.fff,.iiq,.k25,.kdc,.mef,.mos,.mrw,.nef,.nrw,.orf,.pef,.raf,.raw,.rw2,.rwl,.sr2,.srf,.srw,.x3f",
  },
  SpektrafilmLoadImage: {
    widget: "image",
    accept: ".exr,.tif,.tiff,.png,.jpg,.jpeg,.hdr",
  },
};

async function upload(file, combo) {
  const body = new FormData();
  body.append("image", file);
  const resp = await api.fetchApi("/upload/image", { method: "POST", body });
  if (resp.status !== 200) {
    app.extensionManager.toast.add({ severity: "error", summary: "Upload failed", detail: `${file.name}: ${resp.status} ${resp.statusText}`, life: 5000 });
    return;
  }
  const data = await resp.json();
  const name = data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
  if (!combo.options.values.includes(name)) combo.options.values.push(name);
  combo.value = name;
  combo.callback?.(name);
}

app.registerExtension({
  name: "Spektrafilm.Upload",
  nodeCreated(node) {
    const spec = UPLOADS[node.comfyClass];
    if (!spec) return;
    const combo = node.widgets.find((w) => w.name === spec.widget);
    const input = document.createElement("input");
    input.type = "file";
    input.accept = spec.accept;
    input.onchange = async () => {
      if (input.files.length) await upload(input.files[0], combo);
      input.value = "";
    };
    node.addWidget("button", "choose file to upload", null, () => input.click(), { serialize: false });
  },
});
