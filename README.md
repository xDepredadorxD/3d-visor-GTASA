# GTA SA 3D Visor Pro
<img width="1283" height="758" alt="image" src="https://github.com/user-attachments/assets/5c63def0-718c-4125-9e1b-d864a8774d20" />
<img width="1283" height="759" alt="image" src="https://github.com/user-attachments/assets/fea6a6f3-c641-4307-b069-80ab4557767b" />



## ✨ Características Principales

- **Compatibilidad Total**: Carga de archivos `.dff` (geometría) y `.txd` (texturas).
- **Controles Profesionales**:
  - **Orbit**: Clic izquierdo + arrastrar.
  - **Pan**: Clic derecho/central + arrastrar.
  - **Zoom**: Rueda del ratón.
- **Modos de Visión**: Ciclo entre Normal, Maya (Wireframe), Textura + Wire y Sólido + Wire.
- **Gestión de Texturas**: Panel lateral para previsualizar, exportar (PNG) y reemplazar texturas en caliente.
- **Depuración de UV**: Soporte para hasta 2 conjuntos de UV y modo de depuración visual.
- **Alineación Geométrica**: Centrado automático y ajuste al plano del suelo (Y=0).
- **Integración con Windows**: Soporte para *Drag & Drop* y asociación de archivos mediante línea de comandos.
<img width="723" height="747" alt="image" src="https://github.com/user-attachments/assets/d26262d6-ea92-4d7f-b5ff-2980a72a5463" />


## 🚀 Instalación y Uso

### Ejecutable (Recomendado)
Descarga la última versión desde la sección de **Releases** y ejecuta `GTASA_Visor_Pro.exe`.

### Desde el Código Fuente
1. Clona el repositorio:
   ```bash
   git clone https://github.com/xDepredadorxD/3d-visor-GTASA.git
   cd 3d-visor-GTASA
   ```
2. Crea un entorno virtual e instala las dependencias:
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # En Windows
   pip install -r requirements.txt
   ```
3. Ejecuta la aplicación:
   ```bash
   python main.py
   ```

## ⌨️ Atajos de Teclado

| Tecla | Acción |
|---|---|
| `L` | Abrir explorador de archivos para cargar |
| `T` | Mostrar/Ocultar panel de texturas |
| `F` | Voltear coordenadas V (V-Flip) |
| `V` | Cambiar modo de visualización |
| `G` | Alternar Rejilla/Ejes visuales |
| `1-6` | Vistas rápidas (Frente, Atrás, Arriba, etc.) |
| `Ctrl+S` | Guardar cambios en el archivo TXD |

## 🛠️ Compilación (PyInstaller)

Para generar tu propio ejecutable con todas las dependencias incluidas:

```bash
.\venv\Scripts\pyinstaller.exe --noconfirm GTASA_Visor_Pro_v4_Fixed.spec
```

## 🤝 Créditos

- Desarrollado por **xDepredadorxD** - [GitHub Profile](https://github.com/xDepredadorxD)
- RenderRW Parser mejorado para compatibilidad con GTA SA.

---
⭐ Si te gusta este proyecto, ¡no olvides darle una estrella!
