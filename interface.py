import pygame
import moderngl
import numpy as np
from PIL import Image
import os
import time
import tkinter as tk
from tkinter import filedialog
from rw_parser import RWParser


class Button:
    def __init__(
        self,
        x,
        y,
        width,
        height,
        text,
        font,
        bg_color,
        text_color,
        shortcut="",
        icon="",
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.bg_color = bg_color
        self.text_color = text_color
        self.shortcut = shortcut
        self.icon = icon
        self.is_hovered = False
        self.is_pressed = False

    def draw(self, surface):
        color = list(self.bg_color)
        if self.is_pressed:
            color = tuple(max(c - 30, 0) for c in color)
        elif self.is_hovered:
            color = tuple(min(c + 35, 255) for c in color)

        for i in range(self.rect.height):
            t = i / max(self.rect.height - 1, 1)
            r = int(color[0] * (1 - t * 0.25))
            g = int(color[1] * (1 - t * 0.25))
            b = int(color[2] * (1 - t * 0.15))
            pygame.draw.line(
                surface,
                (r, g, b),
                (self.rect.left, self.rect.top + i),
                (self.rect.right - 1, self.rect.top + i),
            )

        border_color = (255, 255, 255, 60) if self.is_hovered else (80, 80, 90, 40)
        pygame.draw.rect(surface, border_color, self.rect, 1, border_radius=6)

        pygame.draw.rect(surface, (0, 0, 0, 30), self.rect.move(0, 2), border_radius=6)
        pygame.draw.rect(surface, color, self.rect, border_radius=6)

        if self.is_hovered:
            highlight = pygame.Surface(
                (self.rect.width, self.rect.height // 2), pygame.SRCALPHA
            )
            pygame.draw.rect(
                highlight, (255, 255, 255, 25), highlight.get_rect(), border_radius=6
            )
            surface.blit(highlight, (self.rect.left, self.rect.top))

        content_x = self.rect.centerx
        if self.icon:
            icon_font = pygame.font.SysFont("segoeuisymbol", 16)
            icon_surf = icon_font.render(self.icon, True, self.text_color)
            icon_rect = icon_surf.get_rect(
                midleft=(self.rect.left + 8, self.rect.centery)
            )
            surface.blit(icon_surf, icon_rect)
            content_x = self.rect.left + 8 + icon_surf.get_width() + 6

        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=(content_x, self.rect.centery))
        surface.blit(text_surf, text_rect)

        if self.shortcut:
            s_font = pygame.font.SysFont("consolas", 10)
            s_surf = s_font.render(f"[{self.shortcut}]", True, (160, 160, 170))
            surface.blit(s_surf, (self.rect.right - 28, self.rect.bottom - 13))

    def update(self, mouse_pos):
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        mouse_down = pygame.mouse.get_pressed()[0]
        self.is_pressed = self.is_hovered and mouse_down

    def is_clicked(self, mouse_pos, mouse_down):
        return self.rect.collidepoint(mouse_pos) and mouse_down


class Interface:
    def __init__(self, screen_size):
        self.screen_size = screen_size
        self.font = None
        self.small_font = None
        self.overlay_prog = None
        self.DEBUG_DIR = "debug_textures"

        # Initialize pygame and font
        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 18)
        self.small_font = pygame.font.SysFont("consolas", 16)

        # Create debug directory
        if not os.path.exists(self.DEBUG_DIR):
            os.makedirs(self.DEBUG_DIR)

        # State variables
        self.current_models = []
        self.textures_cache = {}
        self.show_textures = True
        self.debug_uv_mode = False
        self.active_uv_set = 0
        self.flip_v = True
        self.view_mode_style = "NORMAL"
        self.show_helpers = True

        # Scrolling states for right panel
        self.panel_scroll = 0
        self.panel_rect = pygame.Rect(0, 0, 0, 0)
        self.content_height = 0
        self.visible_height = 0
        self.is_dragging_scrollbar = False
        self.texture_surfaces_cache = {}
        self.original_images_cache = {}
        self.current_txd_name = "nuevo_modelo.txd"
        self.current_txd_path = None
        self.current_dff_path = None
        self.scroll_track_rect = pygame.Rect(0, 0, 0, 0)
        self.texture_rects = {}
        self.context_menu = None

        # UI Palette
        self.COLORS = {
            "primary": (70, 130, 180),
            "secondary": (60, 60, 65),
            "accent": (255, 165, 0),
            "text": (255, 255, 255),
            "bg": (35, 35, 40, 200),
        }

        # UI elements
        self.buttons = []
        self.panel_buttons = []
        self.load_button = None

        self.build_buttons()

        # Create overlay shader
        self.create_overlay_shader()

    def build_buttons(self):
        w = self.screen_size[0]
        btn_h = 28
        gap = 5
        btn_configs = [
            {
                "text": "Cargar",
                "color": self.COLORS["primary"],
                "shortcut": "L",
                "icon": "",
            },
            {
                "text": "Texturas",
                "color": self.COLORS["secondary"],
                "shortcut": "T",
                "icon": "",
            },
            {
                "text": "V-Flip",
                "color": self.COLORS["secondary"],
                "shortcut": "F",
                "icon": "",
            },
            {
                "text": "UV Debug",
                "color": self.COLORS["secondary"],
                "shortcut": "U",
                "icon": "",
            },
            {
                "text": "Visión",
                "color": self.COLORS["secondary"],
                "shortcut": "V",
                "icon": "",
            },
            {
                "text": "Guardar Cambios",
                "color": tuple(min(c + 30, 255) for c in self.COLORS["primary"]),
                "shortcut": "Ctrl+S",
                "icon": "",
            },
            {
                "text": "Rejilla/Ejes",
                "color": self.COLORS["secondary"],
                "shortcut": "G",
                "icon": "",
            },
        ]

        total_width = sum(
            self.small_font.size(c["text"])[0] + 24 for c in btn_configs
        ) + gap * (len(btn_configs) - 1)

        self.buttons = []
        x = 10
        for cfg in btn_configs:
            btn_w = self.small_font.size(cfg["text"])[0] + 24
            self.buttons.append(
                Button(
                    x,
                    5,
                    btn_w,
                    btn_h,
                    cfg["text"],
                    self.small_font,
                    cfg["color"],
                    self.COLORS["text"],
                    cfg["shortcut"],
                    cfg["icon"],
                )
            )
            x += btn_w + gap

        self.load_button = self.buttons[0]

        self.panel_buttons = [
            Button(
                0,
                0,
                110,
                25,
                "Exportar Todo",
                self.small_font,
                self.COLORS["secondary"],
                self.COLORS["text"],
            ),
            Button(
                0,
                0,
                130,
                25,
                "Reemplazar Todo",
                self.small_font,
                self.COLORS["secondary"],
                self.COLORS["text"],
            ),
        ]

    def rebuild_buttons(self):
        self.build_buttons()

    def create_overlay_shader(self):
        """Create shader for rendering text overlay"""
        ctx = moderngl.get_context()
        self.overlay_prog = ctx.program(
            vertex_shader="""
            #version 330
            in vec2 pos;
            out vec2 uv;
            void main() {
                uv = pos * 0.5 + 0.5;
                gl_Position = vec4(pos, 0.0, 1.0);
            }
            """,
            fragment_shader="""
            #version 330
            uniform sampler2D tex;
            in vec2 uv;
            out vec4 fragColor;
            void main() {
                // Sencillo: Muestrear directamente sin flip adicional
                fragColor = texture(tex, uv);
            }
            """,
        )

    def draw_ui(self):
        """Draw ALL UI elements (menu, info) as a single OpenGL overlay"""
        ctx = moderngl.get_context()
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)

        # 1. Create a transparent surface for the entire UI
        ui_surf = pygame.Surface(self.screen_size, pygame.SRCALPHA)

        # --- Top Menu Bar ---
        pygame.draw.rect(ui_surf, self.COLORS["bg"], (0, 0, self.screen_size[0], 40))
        pygame.draw.line(ui_surf, (80, 80, 80), (0, 40), (self.screen_size[0], 40), 1)

        # Update and Draw buttons
        mouse_pos = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(mouse_pos)
            btn.draw(ui_surf)

        # --- Bottom Info Bar ---
        if self.current_models:
            bar_h = 35
            bar_y = self.screen_size[1] - bar_h
            pygame.draw.rect(
                ui_surf, (25, 25, 30, 230), (0, bar_y, self.screen_size[0], bar_h)
            )
            pygame.draw.line(
                ui_surf, (80, 80, 80), (0, bar_y), (self.screen_size[0], bar_y), 1
            )

            dff_name = (
                os.path.splitext(os.path.basename(self.current_dff_path))[0]
                if self.current_dff_path
                else "desconocido"
            )

            dff_size_mb = 0.0
            if self.current_dff_path and os.path.exists(self.current_dff_path):
                dff_size_mb = os.path.getsize(self.current_dff_path) / (1024 * 1024)

            total_verts = 0
            for m in self.current_models:
                total_verts += m.vbo.size // (3 * 4)

            txd_size_mb = 0.0
            if self.current_txd_path and os.path.exists(self.current_txd_path):
                txd_size_mb = os.path.getsize(self.current_txd_path) / (1024 * 1024)

            tex_count = len(self.textures_cache)

            info_text = f"  {dff_name}  |  DFF {dff_size_mb:.2f} Mb  |  Vértices {total_verts}  |  TXD {txd_size_mb:.2f} Mb  |  Texturas {tex_count}  "
            info_surf = self.small_font.render(info_text, True, (220, 220, 220))
            ui_surf.blit(info_surf, (5, bar_y + 8))

        # --- Footer Credits ---
        credit_text = "https://github.com/xDepredadorxD"
        credit_surf = self.small_font.render(credit_text, True, (100, 100, 110))
        ui_surf.blit(
            credit_surf,
            (self.screen_size[0] - credit_surf.get_width() - 10, self.screen_size[1] - 22),
        )

        # --- Right Textures Panel ---
        if self.texture_surfaces_cache:
            PANEL_W = 280
            panel_rect = pygame.Rect(
                self.screen_size[0] - PANEL_W, 40, PANEL_W, self.screen_size[1] - 40
            )
            self.panel_rect = panel_rect  # store for event handling

            # Panel Background
            pygame.draw.rect(ui_surf, self.COLORS["bg"], panel_rect)
            pygame.draw.line(
                ui_surf,
                (80, 80, 80),
                (panel_rect.left, panel_rect.top),
                (panel_rect.left, panel_rect.bottom),
                1,
            )

            # Title Area (Fixed)
            header_rect = pygame.Rect(panel_rect.left, panel_rect.top, PANEL_W, 70)
            pygame.draw.rect(ui_surf, self.COLORS["secondary"], header_rect)
            pygame.draw.line(
                ui_surf,
                (80, 80, 80),
                (header_rect.left, header_rect.bottom),
                (header_rect.right, header_rect.bottom),
                1,
            )

            title_surf = self.font.render("Texturas", True, self.COLORS["text"])
            ui_surf.blit(
                title_surf,
                (
                    header_rect.centerx - title_surf.get_width() // 2,
                    header_rect.top + 8,
                ),
            )

            # Position and draw panel sub-actions
            self.panel_buttons[0].rect.topleft = (
                header_rect.left + 15,
                header_rect.top + 38,
            )
            self.panel_buttons[1].rect.topleft = (
                header_rect.right - 145,
                header_rect.top + 38,
            )
            for btn in self.panel_buttons:
                btn.update(mouse_pos)
                btn.draw(ui_surf)

            # Scrolling Content Area
            content_rect = pygame.Rect(
                panel_rect.left,
                header_rect.bottom,
                PANEL_W,
                panel_rect.height - header_rect.height,
            )
            self.visible_height = content_rect.height

            old_clip = ui_surf.get_clip()
            ui_surf.set_clip(content_rect)

            y_offset = content_rect.top + 20 - self.panel_scroll
            box_size = PANEL_W - 60  # 30 margin on each side for the square

            self.texture_rects.clear()

            for name, surf in self.texture_surfaces_cache.items():
                # Draw Texture Label
                name_surf = self.small_font.render(name, True, (200, 200, 200))
                ui_surf.blit(name_surf, (content_rect.left + 30, y_offset))
                y_offset += 25

                # Draw image square background
                box_rect = pygame.Rect(
                    content_rect.left + 30, y_offset, box_size, box_size
                )
                pygame.draw.rect(ui_surf, (40, 40, 45, 200), box_rect, border_radius=4)
                pygame.draw.rect(
                    ui_surf, (100, 100, 100, 150), box_rect, 1, border_radius=4
                )

                # Store absolute hit rect
                # Make sure it's within clipping bounds to be clickable? Not strictly necessary here since mouse handler checks
                self.texture_rects[name] = box_rect

                # Draw Texture inside the square (centered)
                surf_w, surf_h = surf.get_size()
                img_x = box_rect.centerx - surf_w // 2
                img_y = box_rect.centery - surf_h // 2
                ui_surf.blit(surf, (img_x, img_y))

                y_offset += box_size + 20  # Item margin bottom

            self.content_height = y_offset + self.panel_scroll - content_rect.top

            ui_surf.set_clip(old_clip)

            # Draw Scrollbar
            if self.content_height > self.visible_height:
                self.scroll_track_rect = pygame.Rect(
                    panel_rect.right - 15, content_rect.top, 15, self.visible_height
                )
                pygame.draw.rect(ui_surf, (30, 30, 35, 150), self.scroll_track_rect)

                thumb_h = max(
                    30,
                    int(
                        self.visible_height
                        * (self.visible_height / self.content_height)
                    ),
                )
                thumb_y = content_rect.top + int(
                    (self.panel_scroll / (self.content_height - self.visible_height))
                    * (self.visible_height - thumb_h)
                )

                scroll_thumb_rect = pygame.Rect(
                    panel_rect.right - 13, thumb_y, 11, thumb_h
                )

                # Highlight scrollbar if dragging
                thumb_color = (
                    (150, 150, 150, 200)
                    if self.is_dragging_scrollbar
                    else (120, 120, 120, 200)
                )
                pygame.draw.rect(
                    ui_surf, thumb_color, scroll_thumb_rect, border_radius=5
                )
            else:
                self.panel_scroll = 0
                self.scroll_track_rect = pygame.Rect(0, 0, 0, 0)

        # Draw Context Menu overlay if active
        if self.context_menu:
            cm = self.context_menu
            cm["rects"].clear()
            cx, cy = cm["pos"]

            # Simple menu drawing
            menu_w = 160
            item_h = 30
            menu_h = len(cm["items"]) * item_h

            # Keep on screen
            if cy + menu_h > self.screen_size[1]:
                cy = self.screen_size[1] - menu_h
            if cx + menu_w > self.screen_size[0]:
                cx = self.screen_size[0] - menu_w

            menu_rect = pygame.Rect(cx, cy, menu_w, menu_h)
            pygame.draw.rect(ui_surf, (45, 45, 50, 240), menu_rect)
            pygame.draw.rect(ui_surf, (100, 100, 110), menu_rect, 1)

            my = cy
            mouse_pos = pygame.mouse.get_pos()
            for text in cm["items"]:
                rt = pygame.Rect(cx, my, menu_w, item_h)
                cm["rects"].append(rt)

                if rt.collidepoint(mouse_pos):
                    pygame.draw.rect(ui_surf, (70, 130, 180, 200), rt)

                t_surf = self.small_font.render(text, True, (255, 255, 255))
                ui_surf.blit(
                    t_surf, (cx + 10, my + (item_h - t_surf.get_height()) // 2)
                )
                my += item_h

        # 2. Upload to OpenGL and render
        # flipped=True ensures Pygame's Top (0,0) becomes OpenGL's Top (UV 1)
        data = pygame.image.tostring(ui_surf, "RGBA", True)
        tex = ctx.texture(self.screen_size, 4, data)

        # Quad for full screen overlay
        vbo = ctx.buffer(
            np.array(
                [[-1.0, -1.0], [1.0, -1.0], [-1.0, 1.0], [1.0, 1.0]], "f4"
            ).tobytes()
        )

        vao = ctx.vertex_array(self.overlay_prog, [(vbo, "2f", "pos")])
        tex.use(location=0)
        self.overlay_prog["tex"].value = 0
        vao.render(moderngl.TRIANGLE_STRIP)

        # Cleanup
        vao.release()
        vbo.release()
        tex.release()
        ctx.enable(moderngl.DEPTH_TEST)

    # draw_rotation_info is now merged into draw_ui

    def load_file(self, files=None):
        """Load 3D model files, returns list of all vertex arrays for camera framing"""
        global current_models, textures_cache

        if files is None:
            root = tk.Tk()
            root.withdraw()
            files = filedialog.askopenfilenames(
                filetypes=[("GTA SA assets", "*.dff *.txd")]
            )
            root.destroy()
            if not files:
                return None
        
        # Ensure we have a list/tuple of strings
        if isinstance(files, str):
            files = [files]
        dff_path = next((f for f in files if f.lower().endswith(".dff")), None)
        txd_paths = [f for f in files if f.lower().endswith(".txd")]
        if not dff_path and not txd_paths:
            return None

        # Clear existing models ONLY if a new DFF was selected
        if dff_path:
            for m in self.current_models:
                m.release()
            self.current_models = []

        # Always clear texture cache to show the newly loaded TXD
        self.textures_cache = {}
        self.texture_surfaces_cache = {}
        self.original_images_cache = {}
        self.panel_scroll = 0

        self.current_txd_name = (
            os.path.basename(txd_paths[0]) if txd_paths else "nuevo_modelo.txd"
        )

        t0 = time.time()

        try:
            # ── TXD ────────────────────────────────────────────
            txd_files_to_load = txd_paths
            if dff_path and not txd_paths:
                auto = dff_path.lower().replace(".dff", ".txd")
                # Need original case to actually load in OS
                auto_real = dff_path[:-4] + ".txd"
                if os.path.exists(auto_real):
                    txd_files_to_load = [auto_real]

            self.current_txd_path = txd_files_to_load[0] if txd_files_to_load else None
            self.current_dff_path = dff_path

            for tp in txd_files_to_load:
                print(f"\n[LOAD TXD] {os.path.basename(tp)}")
                for name, img in RWParser.parse_txd(tp).items():
                    if not img:
                        continue
                    # Load texture to GPU
                    data = img.convert("RGBA").tobytes()
                    ctx = moderngl.get_context()
                    tex = ctx.texture(img.size, 4, data, alignment=1)
                    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
                    tex.repeat_x = True
                    tex.repeat_y = True
                    tex.build_mipmaps()
                    self.textures_cache[name.lower()] = tex
                    self.original_images_cache[name.lower()] = img.copy()

                    # Store scaled pygame surface for right panel
                    pg_img = pygame.image.fromstring(data, img.size, "RGBA")
                    box_size = 280 - 60
                    surf_w, surf_h = pg_img.get_size()
                    scale = min(box_size / surf_w, box_size / surf_h)
                    new_w, new_h = (
                        max(1, int(surf_w * scale)),
                        max(1, int(surf_h * scale)),
                    )
                    if scale >= 1.0:
                        scaled_img = pygame.transform.scale(pg_img, (new_w, new_h))
                    else:
                        scaled_img = pygame.transform.smoothscale(pg_img, (new_w, new_h))
                    self.texture_surfaces_cache[name.lower()] = scaled_img

                    print(f"    + tex '{name}' {img.size}")

            # If we only loaded a TXD, update the live models and skip DFF parsing
            if not dff_path:
                for m in self.current_models:
                    if hasattr(m, "material_name"):
                        new_tex = self.textures_cache.get(m.material_name.lower())
                        if new_tex:
                            m.replace_texture(m.material_name, new_tex)
                print(f"[OK] TXD cargado en {time.time() - t0:.2f}s")
                return None

            # ── DFF ────────────────────────────────────────────
            print(f"\n[LOAD DFF] {os.path.basename(dff_path)}")
            from model import Model

            dff = RWParser.parse_dff(dff_path)
            all_v = []
            for geom in dff["geometries"]:
                mat = geom["materials"][0].lower() if geom["materials"] else ""
                tex = self.textures_cache.get(mat)
                match = "OK" if tex else "NO"
                print(
                    f"  GEO verts={len(geom['vertices'])} tris={len(geom['faces'])} mat='{mat}' {match}"
                )

                m = Model(
                    geom["vertices"],
                    geom.get("uv_sets", []),
                    geom["normals"],
                    geom["faces"],
                    tex,
                )
                m.material_name = (
                    mat  # Store the material name for context menu replacement
                )
                m.set_uv_index(self.active_uv_set, self.flip_v)
                self.current_models.append(m)
                all_v.append(geom["vertices"])

            print(f"[OK] {len(self.current_models)} parts | {time.time() - t0:.2f}s")
            return all_v

        except Exception:
            import traceback

            traceback.print_exc()


        self.active_uv_set += increment
        for m in self.current_models:
            m.set_uv_index(self.active_uv_set, self.flip_v)
        print(f"[UV SET] Seleccionado Set {self.active_uv_set}")

    def toggle_flip_v(self):
        """Toggle V coordinate flipping"""
        self.flip_v = not self.flip_v
        for m in self.current_models:
            m.set_uv_index(self.active_uv_set, self.flip_v)
        print(f"[V-FLIP] {'Activado' if self.flip_v else 'Desactivado'}")

    def toggle_debug_uv(self):
        self.debug_uv_mode = not self.debug_uv_mode

    def cycle_view_mode(self):
        modes = ["NORMAL", "WIREFRAME", "TEXTURE_WIRE", "SOLID_WIRE"]
        names = {
            "NORMAL": "Normal",
            "WIREFRAME": "Maya",
            "TEXTURE_WIRE": "M+T",
            "SOLID_WIRE": "M+P",
        }
        idx = modes.index(self.view_mode_style)
        self.view_mode_style = modes[(idx + 1) % len(modes)]
        self.buttons[4].text = f"[{names[self.view_mode_style]}]"
        mode = "UV DEBUG (rojo=U, verde=V)" if self.debug_uv_mode else "Normal"
        print(f"[MODE] {mode}")
        # Note: Caption update would be handled in main loop
        return mode

    def handle_wheel(self, y_amount, mouse_pos):
        if self.texture_surfaces_cache and self.panel_rect.collidepoint(mouse_pos):
            self.panel_scroll -= y_amount * 40
            max_scroll = max(0, self.content_height - self.visible_height)
            self.panel_scroll = max(0, min(self.panel_scroll, max_scroll))
            return True
        return False

    def handle_mouse_down(self, pos, button=1):
        if self.context_menu:
            if button == 1:
                clicked_item = None
                for i, rect in enumerate(self.context_menu["rects"]):
                    if rect.collidepoint(pos):
                        clicked_item = self.context_menu["items"][i]
                        break

                target = self.context_menu["target"]
                self.context_menu = None

                if clicked_item:
                    self.execute_context_action(clicked_item, target)
                    return True

                return True
            else:
                self.context_menu = None
                return False

        if not self.texture_surfaces_cache:
            return False

        if button == 1:
            if (
                self.scroll_track_rect.collidepoint(pos)
                and self.content_height > self.visible_height
            ):
                self.is_dragging_scrollbar = True
                self.update_scroll_from_mouse(pos[1])
                return True
            elif self.panel_rect.collidepoint(pos):
                if self.panel_buttons[0].rect.collidepoint(pos):
                    self.export_all_textures()
                elif self.panel_buttons[1].rect.collidepoint(pos):
                    self.replace_all_textures()
                return True
        elif button == 3:  # Right click
            if self.panel_rect.collidepoint(pos):
                # Only if the mouse is in the content region (cliped region)
                content_rect = pygame.Rect(
                    self.panel_rect.left,
                    self.panel_rect.top + 40,
                    self.panel_rect.width,
                    self.panel_rect.height - 40,
                )
                if content_rect.collidepoint(pos):
                    # Check which texture rect
                    for name, rect in self.texture_rects.items():
                        if rect.collidepoint(pos):
                            self.open_context_menu(name, pos)
                            break
                return True
        return False

    def handle_mouse_up(self, pos, button=1):
        if button == 1:
            self.is_dragging_scrollbar = False

    def handle_mouse_motion(self, pos):
        if hasattr(self, "is_dragging_scrollbar") and self.is_dragging_scrollbar:
            self.update_scroll_from_mouse(pos[1])
            return True
        return False

    def update_scroll_from_mouse(self, mouse_y):
        if self.content_height <= self.visible_height:
            return

        track = self.scroll_track_rect
        thumb_h = max(
            30, int(self.visible_height * (self.visible_height / self.content_height))
        )

        rel_y = mouse_y - track.top - thumb_h / 2
        max_y = track.height - thumb_h

        progress = max(0.0, min(1.0, rel_y / max_y if max_y > 0 else 0))
        self.panel_scroll = progress * (self.content_height - self.visible_height)

    def open_context_menu(self, target_name, pos):
        self.context_menu = {
            "pos": pos,
            "items": ["Exportar PNG", "Reemplazar", "Eliminar", "Guardar TXD"],
            "rects": [],
            "target": target_name,
        }

    def execute_context_action(self, action, target_name):
        if action == "Exportar PNG":
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            path = filedialog.asksaveasfilename(
                defaultextension=".png",
                initialfile=f"{target_name}.png",
                filetypes=[("PNG", "*.png")],
            )
            root.destroy()
            if path:
                if target_name.lower() in getattr(self, "original_images_cache", {}):
                    self.original_images_cache[target_name.lower()].save(path)
                    print(f"[TXD] Exportado a {path}")

        elif action == "Reemplazar":
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            path = filedialog.askopenfilename(
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga")]
            )
            root.destroy()
            if path:
                try:
                    img = Image.open(path).convert("RGBA")

                    # Inherit all original DXT/TXD metadata, EXCEPT the raw bytes chunk
                    # so rw_parser knows it has been modified and recompresses it correctly
                    if target_name.lower() in self.original_images_cache:
                        old_meta = self.original_images_cache[
                            target_name.lower()
                        ].info.copy()
                        old_meta.pop("txd_raw_chunk", None)  # Remove raw chunk
                        img.info.update(old_meta)

                    # Update ModernGL texture bounds
                    data = img.tobytes()
                    ctx = moderngl.get_context()
                    tex = ctx.texture(img.size, 4, data, alignment=1)
                    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
                    tex.build_mipmaps()

                    self.textures_cache[target_name.lower()] = tex
                    self.original_images_cache[target_name.lower()] = img.copy()

                    # Update panel cache surface
                    pg_img = pygame.image.fromstring(data, img.size, "RGBA")
                    box_size = 280 - 60
                    surf_w, surf_h = pg_img.get_size()
                    scale = min(box_size / surf_w, box_size / surf_h)
                    new_w, new_h = (
                        max(1, int(surf_w * scale)),
                        max(1, int(surf_h * scale)),
                    )
                    scaled_img = pygame.transform.smoothscale(pg_img, (new_w, new_h))

                    self.texture_surfaces_cache[target_name] = scaled_img

                    # Update model materials reference
                    for m in self.current_models:
                        # Rebuild model textures internally if we have to,
                        # but if we just replaced it in cache, it won't retroactively apply because Model stores the texture ref directly.
                        # So we need to reassign texture in the model
                        m.replace_texture(target_name.lower(), tex)

                    print(
                        f"[TXD] Textura '{target_name}' reemplazada por '{os.path.basename(path)}'"
                    )
                except Exception as e:
                    print(f"Error reemplazando textura: {e}")

        elif action == "Eliminar":
            if target_name in self.texture_surfaces_cache:
                del self.texture_surfaces_cache[target_name]
            if target_name.lower() in self.textures_cache:
                self.textures_cache[target_name.lower()].release()
                del self.textures_cache[target_name.lower()]
            if target_name.lower() in self.original_images_cache:
                del self.original_images_cache[target_name.lower()]
            for m in self.current_models:
                if (
                    hasattr(m, "material_name")
                    and m.material_name.lower() == target_name.lower()
                ):
                    m.texture = None
            print(f"[TXD] Textura eliminada: {target_name}")

        elif action == "Guardar TXD":
            from tkinter import filedialog
            from rw_parser import RWParser

            root = tk.Tk()
            root.withdraw()
            initial_name = getattr(self, "current_txd_name", "nuevo_modelo.txd")
            path = filedialog.asksaveasfilename(
                defaultextension=".txd",
                initialfile=initial_name,
                filetypes=[("TXD files", "*.txd")],
            )
            root.destroy()
            if path:
                try:
                    tex_list = []
                    for name, img in getattr(self, "original_images_cache", {}).items():
                        tex_list.append({"name": name, "img": img})

                    if not tex_list:
                        print("[TXD] Eliminada. Reemplaza o dale Guardar TXD.")
                        return

                    RWParser.write_txd(path, tex_list)
                    print(f"[TXD] TXD Guardado en {path}")
                except Exception as e:
                    print(f"Error guardando TXD: {e}")

    def save_current_txd(self):
        if not hasattr(self, "current_txd_path") or not self.current_txd_path:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "Atención",
                "No hay ningún archivo .txd cargado al cual guardar cambios.",
            )
            root.destroy()
            return

        textures_list = []
        for tname, img in self.original_images_cache.items():
            textures_list.append({"name": tname, "img": img})

        try:
            from rw_parser import RWParser
            import time

            RWParser.write_txd(self.current_txd_path, textures_list)
            print(
                f"[{time.strftime('%H:%M:%S')}] Cambios guardados correctamente en: {self.current_txd_path}"
            )
        except Exception as e:
            print(f"Error guardando TXD: {e}")

    def export_all_textures(self):
        if not self.original_images_cache:
            return
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory(title="Seleccionar carpeta de destino")
        root.destroy()
        if folder:
            count = 0
            for name, img in self.original_images_cache.items():
                path = os.path.join(folder, f"{name}.png")
                img.save(path)
                count += 1
                print(f"[TXD] Exportado -> {path}")
            print(f"[TXD] Exportación masiva completada. {count} texturas exportadas.")

    def replace_all_textures(self):
        if not self.original_images_cache:
            return
        from tkinter import filedialog
        import os

        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta de texturas para reemplazo"
        )
        root.destroy()
        if not folder:
            return

        ctx = moderngl.get_context()
        matched_count = 0

        valid_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}
        files = []
        for f in os.listdir(folder):
            if os.path.splitext(f)[1].lower() in valid_exts:
                files.append(os.path.join(folder, f))

        for path in files:
            base_name = os.path.splitext(os.path.basename(path))[0].lower()
            if base_name in self.original_images_cache:
                target_name = base_name
                try:
                    new_img = Image.open(path)
                    new_img.load()

                    old_meta = self.original_images_cache[target_name].info.copy()
                    if "txd_raw_chunk" in old_meta:
                        del old_meta["txd_raw_chunk"]

                    new_img.info = old_meta
                    self.original_images_cache[target_name] = new_img

                    data = new_img.convert("RGBA").tobytes()
                    tex = ctx.texture(new_img.size, 4, data, alignment=1)
                    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
                    tex.repeat_x = True
                    tex.repeat_y = True
                    tex.build_mipmaps()

                    if target_name in self.textures_cache:
                        self.textures_cache[target_name].release()
                    self.textures_cache[target_name] = tex

                    pg_img = pygame.image.fromstring(data, new_img.size, "RGBA")
                    box_size = 280 - 60
                    surf_w, surf_h = pg_img.get_size()
                    scale = min(box_size / surf_w, box_size / surf_h)
                    new_w, new_h = (
                        max(1, int(surf_w * scale)),
                        max(1, int(surf_h * scale)),
                    )
                    scaled_img = pygame.transform.smoothscale(pg_img, (new_w, new_h))
                    self.texture_surfaces_cache[target_name] = scaled_img

                    for m in self.current_models:
                        if (
                            hasattr(m, "material_name")
                            and m.material_name.lower() == target_name
                        ):
                            m.replace_texture(target_name, tex)

                    print(
                        f"[TXD] Reemplazo por lote OK: '{target_name}' con {os.path.basename(path)}"
                    )
                    matched_count += 1
                except Exception as e:
                    print(f"[TXD] Error reemplazando {target_name}: {e}")

        print(
            f"[TXD] Reemplazo múltiple finalizado. {matched_count} coincidencias actualizadas."
        )
