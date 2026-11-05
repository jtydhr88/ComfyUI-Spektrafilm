export interface LiveImage {
  width: number
  height: number
  data: Uint16Array
}

export interface LiveLut {
  size: number
  max: number
  gamma: number
  data: Uint16Array
}

const VERTEX = `#version 300 es
in vec2 a_position;
out vec2 v_uv;
void main() {
  v_uv = vec2(a_position.x * 0.5 + 0.5, 0.5 - a_position.y * 0.5);
  gl_Position = vec4(a_position, 0.0, 1.0);
}`

const FRAGMENT = `#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler2D u_image;
uniform sampler3D u_lut;
uniform float u_max;
uniform float u_gamma;
uniform float u_size;
in vec2 v_uv;
out vec4 fragColor;
void main() {
  vec3 value = texture(u_image, v_uv).rgb;
  vec3 grid = pow(clamp(value / u_max, 0.0, 1.0), vec3(1.0 / u_gamma));
  vec3 coord = (grid * (u_size - 1.0) + 0.5) / u_size;
  fragColor = vec4(texture(u_lut, coord).rgb, 1.0);
}`

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)!
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? 'shader compile failed')
  return shader
}

function texture(gl: WebGL2RenderingContext, target: number): WebGLTexture {
  const tex = gl.createTexture()!
  gl.bindTexture(target, tex)
  gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.texParameteri(target, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(target, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  gl.texParameteri(target, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE)
  return tex
}

export class LutRenderer {
  private gl: WebGL2RenderingContext
  private program: WebGLProgram
  private imageTexture: WebGLTexture
  private lutTexture: WebGLTexture
  private image: LiveImage | null = null

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', { premultipliedAlpha: false, preserveDrawingBuffer: true })
    if (!gl) throw new Error('WebGL2 is not available')
    this.gl = gl
    const program = gl.createProgram()!
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX))
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? 'program link failed')
    this.program = program

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    const position = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)

    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    this.imageTexture = texture(gl, gl.TEXTURE_2D)
    this.lutTexture = texture(gl, gl.TEXTURE_3D)
  }

  draw(image: LiveImage, lut: LiveLut) {
    const gl = this.gl
    gl.useProgram(this.program)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.imageTexture)
    if (image !== this.image) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB16F, image.width, image.height, 0, gl.RGB, gl.HALF_FLOAT, image.data)
      this.image = image
      this.canvas.width = image.width
      this.canvas.height = image.height
    }
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_3D, this.lutTexture)
    gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGB16F, lut.size, lut.size, lut.size, 0, gl.RGB, gl.HALF_FLOAT, lut.data)

    gl.uniform1i(gl.getUniformLocation(this.program, 'u_image'), 0)
    gl.uniform1i(gl.getUniformLocation(this.program, 'u_lut'), 1)
    gl.uniform1f(gl.getUniformLocation(this.program, 'u_max'), lut.max)
    gl.uniform1f(gl.getUniformLocation(this.program, 'u_gamma'), lut.gamma)
    gl.uniform1f(gl.getUniformLocation(this.program, 'u_size'), lut.size)
    gl.viewport(0, 0, this.canvas.width, this.canvas.height)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
  }

  dispose() {
    this.gl.getExtension('WEBGL_lose_context')?.loseContext()
  }
}
