import os
import sys

if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "xdepredador.gtasa.3dvisor.1.0"
        )
    except:
        pass

import pygame
import moderngl
import numpy as np
from pyrr import Matrix44
from PIL import Image

from camera import Camera
from interface import Interface
from model import Model, Grid, AxisGizmo


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def main():
    pygame.init()
    screen_size = [1280, 720]
    pygame.display.set_mode(
        screen_size, pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    )
    pygame.display.set_caption("GTA SA 3D Visor Pro")

    # Set icon
    icon_path = resource_path("dff-txd.ico")
    if os.path.exists(icon_path):
        try:
            ico = Image.open(icon_path)
            ico = ico.convert("RGBA")
            pygame_icon = pygame.image.fromstring(
                ico.tobytes(), ico.size, ico.mode
            ).convert_alpha()
            pygame.display.set_icon(pygame_icon)
        except Exception:
            pass

    ctx = moderngl.create_context()
    camera = Camera(screen_size)
    interface = Interface(screen_size)
    
    # Visual aids
    grid = Grid(size=30, divisions=30)
    gizmo = AxisGizmo(size=1.0)

    def load_model(files=None):
        result = interface.load_file(files)
        if result is not None:
            camera.frame_model(result)
            print(f"[CARGA] Modelo alineado al suelo.")

    # Check for CLI arguments (File Association)
    if len(sys.argv) > 1:
        load_model(sys.argv[1:])

    clock = pygame.time.Clock()
    running = True
    mouse_btn = {1: False, 2: False, 3: False}


    def set_model_face(name):
        camera.set_model_face(name)
        print(f"[MODELO] Cara: {name}")

    def rotate_model(dy, dx):
        camera.rotate_in_camera_space(dy, dx)

    while running:
        mouse_clicked = False
        dt = clock.tick(60) / 1000.0
        
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            
            elif ev.type == pygame.DROPFILE:
                # Handle drag and drop
                print(f"[DROP] Cargando archivo soltado: {ev.file}")
                load_model([ev.file])

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_l:
                    load_model()
                elif ev.key == pygame.K_1: set_model_face("frente")
                elif ev.key == pygame.K_2: set_model_face("derecha")
                elif ev.key == pygame.K_3: set_model_face("atras")
                elif ev.key == pygame.K_4: set_model_face("izquierda")
                elif ev.key == pygame.K_5: set_model_face("arriba")
                elif ev.key == pygame.K_6: set_model_face("abajo")
                elif ev.key == pygame.K_t:
                    interface.show_textures = not interface.show_textures
                elif ev.key == pygame.K_k:
                    interface.update_uv_set(1)
                elif ev.key == pygame.K_f:
                    interface.toggle_flip_v()
                elif ev.key == pygame.K_g:
                    interface.show_helpers = not interface.show_helpers
                elif ev.key == pygame.K_v:
                    interface.cycle_view_mode()
                elif ev.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    interface.save_current_txd()
                elif ev.key == pygame.K_LEFT: rotate_model(0, -1)
                elif ev.key == pygame.K_RIGHT: rotate_model(0, 1)
                elif ev.key == pygame.K_UP: rotate_model(1, 0)
                elif ev.key == pygame.K_DOWN: rotate_model(-1, 0)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if interface.handle_mouse_down(ev.pos, ev.button):
                    pass
                else:
                    if ev.button in mouse_btn:
                        mouse_btn[ev.button] = True
                        if ev.button == 1:
                            mouse_clicked = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                interface.handle_mouse_up(ev.pos, ev.button)
                if ev.button in mouse_btn:
                    mouse_btn[ev.button] = False

            elif ev.type == pygame.MOUSEMOTION:
                if not interface.handle_mouse_motion(ev.pos):
                    dx, dy = ev.rel
                    # Orbit (Left click)
                    if mouse_btn[1]:
                        camera.orbit(dx, dy)
                    # Pan (Right click)
                    elif mouse_btn[3]:
                        camera.pan(dx, dy)
                    # Pan (Middle click)
                    elif mouse_btn[2]:
                        camera.pan(dx, dy)

            elif ev.type == pygame.MOUSEWHEEL:
                if not interface.handle_wheel(ev.y, pygame.mouse.get_pos()):
                    camera.zoom(ev.y)

            elif ev.type == pygame.VIDEORESIZE:
                screen_size = list(ev.size)
                pygame.display.set_mode(
                    screen_size, pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
                )
                ctx.viewport = (0, 0, screen_size[0], screen_size[1])
                interface.screen_size = screen_size
                interface.rebuild_buttons()
                camera.screen_size = screen_size

        if mouse_clicked:
            # Handle UI buttons
            mouse_pos = pygame.mouse.get_pos()
            for i, btn in enumerate(interface.buttons):
                if btn.is_clicked(mouse_pos, True):
                    # Trigger corresponding actions
                    if i == 0: load_model()
                    elif i == 1: interface.show_textures = not interface.show_textures
                    elif i == 2: interface.toggle_flip_v()
                    elif i == 3: interface.toggle_debug_uv()
                    elif i == 4: interface.cycle_view_mode()
                    elif i == 5: interface.save_current_txd()
                    elif i == 6: interface.show_helpers = not interface.show_helpers

        ctx.clear(0.12, 0.12, 0.14)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.BLEND)

        # Matrices
        view = camera.get_view_matrix()
        proj = camera.get_projection_matrix()
        mvp = proj * view
        model_mat = camera.get_model_matrix()

        # Render Helper visual aids
        if interface.show_helpers:
            grid.render(mvp)
            gizmo.render(mvp)

        # Render Models
        if interface.view_mode_style == "NORMAL":
            for m in interface.current_models:
                m.render(mvp, model_mat, interface.show_textures, interface.debug_uv_mode)
        elif interface.view_mode_style == "WIREFRAME":
            ctx.wireframe = True
            for m in interface.current_models:
                m.render(mvp, model_mat, False, False, is_wireframe=True)
            ctx.wireframe = False
        elif interface.view_mode_style == "TEXTURE_WIRE":
            for m in interface.current_models:
                m.render(mvp, model_mat, interface.show_textures, False)
            ctx.wireframe = True
            for m in interface.current_models:
                m.render(mvp, model_mat, False, False, is_wireframe=True)
            ctx.wireframe = False
        elif interface.view_mode_style == "SOLID_WIRE":
            for m in interface.current_models:
                m.render(mvp, model_mat, False, False)
            ctx.wireframe = True
            for m in interface.current_models:
                m.render(mvp, model_mat, False, False, is_wireframe=True)
            ctx.wireframe = False

        interface.draw_ui()
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
