import moderngl
import numpy as np

# Create shaders as module-level constants
VERTEX_SHADER = """
#version 330
in vec3 in_pos;
in vec2 in_uv;
in vec3 in_norm;

out vec2 uv;
out vec3 norm;

uniform mat4 mvp;
uniform mat4 model;

void main() {
    uv   = in_uv;
    norm = mat3(model) * in_norm;
    gl_Position = mvp * model * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330
in vec2 uv;
in vec3 norm;
out vec4 fragColor;

uniform sampler2D tex;
uniform bool has_tex;
uniform bool show_tex;
uniform bool debug_uv;   // [U] key: show UV coords as R/G colours
uniform bool is_wireframe;

void main() {
    if (is_wireframe) {
        fragColor = vec4(0.0, 1.0, 0.0, 1.0); // Verde brillante para la maya
        return;
    }

    vec3 L = normalize(vec3(0.6, 0.8, 1.0));
    float diff = max(abs(dot(normalize(norm), L)), 0.25);
    float shade = diff + 0.25;

    if (debug_uv) {
        // UV debug: U=red channel, V=green channel
        fragColor = vec4(uv.x, uv.y, 0.0, 1.0);
        return;
    }

    vec4 col = vec4(0.78, 0.78, 0.78, 1.0);
    if (has_tex && show_tex) {
        col = texture(tex, uv);
        if (col.a < 0.1) discard;
    }
    fragColor = vec4(col.rgb * shade, col.a);
}
"""

# Global shader program (initialized once)
_prog = None


def get_shader_program():
    """Get or create the shader program (singleton pattern)"""
    global _prog
    if _prog is None:
        ctx = moderngl.get_context()
        _prog = ctx.program(
            vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER
        )
        if "tex" in _prog:
            _prog["tex"].value = 0
    return _prog


class Model:
    def __init__(self, vertices, uv_sets, normals, faces, texture=None):
        ctx = moderngl.get_context()
        prog = get_shader_program()

        self.texture = texture
        self.uv_sets = uv_sets
        n = len(vertices)

        # Pad / validate arrays to match vertex count
        if not self.uv_sets:
            self.uv_sets = [np.zeros((n, 2), "f4")]

        active_uvs = self.uv_sets[0]

        if normals is None or len(normals) != n:
            normals = np.zeros((n, 3), "f4")

        self.vbo = ctx.buffer(vertices.astype("f4").tobytes())
        self.uvbo = ctx.buffer(active_uvs.astype("f4").tobytes())
        self.nbo = ctx.buffer(normals.astype("f4").tobytes())
        self.ibo = ctx.buffer(faces.astype("i4").tobytes())

        self.vao = ctx.vertex_array(
            prog,
            [
                (self.vbo, "3f", "in_pos"),
                (self.uvbo, "2f", "in_uv"),
                (self.nbo, "3f", "in_norm"),
            ],
            index_buffer=self.ibo,
        )

    def render(self, mvp, model_mat, show_tex, debug_uv=False, is_wireframe=False):
        prog = get_shader_program()
        prog["mvp"].write(mvp.astype("f4").tobytes())
        prog["model"].write(model_mat.astype("f4").tobytes())
        prog["show_tex"].value = show_tex
        prog["debug_uv"].value = debug_uv
        if "is_wireframe" in prog:
            prog["is_wireframe"].value = is_wireframe
            
        if self.texture and show_tex and not debug_uv and not is_wireframe:
            self.texture.use(location=0)
            prog["tex"].value = 0
            prog["has_tex"].value = True
        else:
            prog["has_tex"].value = False
        self.vao.render()

    def set_uv_index(self, index, flip_v=False):
        if not self.uv_sets:
            return
        idx = index % len(self.uv_sets)
        uvs = self.uv_sets[idx].copy()
        if flip_v:
            uvs[:, 1] = 1.0 - uvs[:, 1]
        self.uvbo.write(uvs.astype("f4").tobytes())

    def replace_texture(self, material_name, new_texture):
        # We need a way to check if this model uses the replaced texture
        # Currently the Model class doesn't store its material name, so we add it dynamically or just set it
        if hasattr(self, 'material_name') and self.material_name.lower() == material_name.lower():
            self.texture = new_texture

    def release(self):
        for r in (self.vbo, self.uvbo, self.nbo, self.ibo, self.vao):
            r.release()

class Grid:
    def __init__(self, size=20.0, divisions=20):
        ctx = moderngl.get_context()
        self.prog = ctx.program(
            vertex_shader="""
            #version 330
            uniform mat4 mvp;
            in vec3 in_pos;
            void main() {
                gl_Position = mvp * vec4(in_pos, 1.0);
            }
            """,
            fragment_shader="""
            #version 330
            out vec4 fragColor;
            void main() {
                fragColor = vec4(0.3, 0.3, 0.35, 1.0);
            }
            """
        )
        
        verts = []
        step = size / divisions
        start = -size / 2
        for i in range(divisions + 1):
            # Lines along X
            verts.extend([start, 0, start + i * step])
            verts.extend([start + size, 0, start + i * step])
            # Lines along Z
            verts.extend([start + i * step, 0, start])
            verts.extend([start + i * step, 0, start + size])
        
        self.vbo = ctx.buffer(np.array(verts, "f4").tobytes())
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, "3f", "in_pos")])

    def render(self, mvp):
        self.prog["mvp"].write(mvp.astype("f4").tobytes())
        self.vao.render(moderngl.LINES)

class AxisGizmo:
    def __init__(self, size=1.0):
        ctx = moderngl.get_context()
        self.prog = ctx.program(
            vertex_shader="""
            #version 330
            uniform mat4 mvp;
            in vec3 in_pos;
            in vec3 in_col;
            out vec3 col;
            void main() {
                col = in_col;
                gl_Position = mvp * vec4(in_pos, 1.0);
            }
            """,
            fragment_shader="""
            #version 330
            in vec3 col;
            out vec4 fragColor;
            void main() {
                fragColor = vec4(col, 1.0);
            }
            """
        )
        # X=Red, Y=Green, Z=Blue
        verts = [
            0, 0, 0, 1, 0, 0,  size, 0, 0, 1, 0, 0,
            0, 0, 0, 0, 1, 0,  0, size, 0, 0, 1, 0,
            0, 0, 0, 0, 0, 1,  0, 0, size, 0, 0, 1,
        ]
        self.vbo = ctx.buffer(np.array(verts, "f4").tobytes())
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, "3f 3f", "in_pos", "in_col")])

    def render(self, mvp):
        self.prog["mvp"].write(mvp.astype("f4").tobytes())
        self.vao.render(moderngl.LINES)
