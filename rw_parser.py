"""
rw_parser.py  –  GTA San Andreas DFF + TXD professional parser
Implements BinMesh PLG (Extension 0x050E) for correct per-material sub-mesh splitting.
Based on GTAmods.com wiki + DragonFF reference implementation.
"""

import struct
import numpy as np
from PIL import Image
import os


class RWParser:
    # Chunk types
    CHUNK_STRUCT             = 0x01
    CHUNK_STRING             = 0x02
    CHUNK_EXTENSION          = 0x03
    CHUNK_TEXTURE            = 0x06
    CHUNK_MATERIAL           = 0x07
    CHUNK_MATERIAL_LIST      = 0x08
    CHUNK_FRAME_LIST         = 0x0E
    CHUNK_GEOMETRY           = 0x0F
    CHUNK_CLUMP              = 0x10
    CHUNK_TEXNATIVE          = 0x15
    CHUNK_TEXTURE_DICTIONARY = 0x16
    CHUNK_GEOMETRY_LIST      = 0x1A
    CHUNK_BINMESH_PLG        = 0x050E   # BinMesh Plugin inside Extension

    # Geometry flags (lower 16 bits of the flags uint32)
    FLAG_TRISTRIP  = 0x0001
    FLAG_POSITIONS = 0x0002
    FLAG_TEXCOORDS = 0x0004
    FLAG_COLORS    = 0x0008
    FLAG_NORMALS   = 0x0010
    FLAG_MODULATE  = 0x0040
    FLAG_TEXCOORDS2= 0x0080

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def read_chunk_header(f):
        data = f.read(12)
        if len(data) < 12:
            return 0, 0, 0
        return struct.unpack("<III", data)

    # ------------------------------------------------------------------ #
    #  DFF                                                                 #
    # ------------------------------------------------------------------ #
    @classmethod
    def parse_dff(cls, path):
        with open(path, "rb") as f:
            ct, cs, cv = cls.read_chunk_header(f)
            if ct == cls.CHUNK_CLUMP:
                return cls._parse_clump(f, cs)
        return {"geometries": []}

    @classmethod
    def _parse_clump(cls, f, size):
        end = f.tell() + size
        geometries = []
        while f.tell() < end - 11:
            ct, cs, cv = cls.read_chunk_header(f)
            chunk_end = f.tell() + cs
            if ct == cls.CHUNK_GEOMETRY_LIST:
                geometries = cls._parse_geometry_list(f, cs)
            f.seek(chunk_end)
        return {"geometries": geometries}

    @classmethod
    def _parse_geometry_list(cls, f, size):
        end = f.tell() + size
        geometries = []

        # Struct sub-chunk → num_geometries
        st, ss, sv = cls.read_chunk_header(f)
        num_geoms = struct.unpack("<I", f.read(4))[0]
        leftover = ss - 4
        if leftover > 0: f.seek(leftover, 1)

        print(f"   [GEO LIST] {num_geoms} geometria(s)")

        while len(geometries) < num_geoms and f.tell() < end - 11:
            ct, cs, cv = cls.read_chunk_header(f)
            chunk_end = f.tell() + cs
            if ct == cls.CHUNK_GEOMETRY:
                try:
                    geoms = cls._parse_geometry(f, cs)
                    geometries.extend(geoms)   # BinMesh may split 1 geo → N sub-meshes
                except Exception as e:
                    import traceback; traceback.print_exc()
                    print(f"   [WARN] Saltando geometria: {e}")
            f.seek(chunk_end)

        return geometries

    @classmethod
    def _parse_geometry(cls, f, size):
        """
        Returns a LIST of sub-mesh dicts (one per material group).
        Each dict: { vertices, uvs, normals, faces, materials: [name] }
        """
        geo_start = f.tell()
        geo_end   = geo_start + size

        # ---------- Struct sub-chunk ----------
        cls.read_chunk_header(f)
        flags_val        = struct.unpack("<I", f.read(4))[0]
        flags            = flags_val & 0xFFFF

        # Bits 16-23 = numTexCoordSets (per GTAmods spec + DragonFF)
        # If 0: TEXTURED2 → 2 sets, TEXTURED → 1 set,  else 0
        tex_count_raw = (flags_val & 0x00FF0000) >> 16
        has_tex  = bool(flags & cls.FLAG_TEXCOORDS)
        has_tex2 = bool(flags & cls.FLAG_TEXCOORDS2)
        if has_tex or has_tex2:
            num_uvs_packed = tex_count_raw
            if num_uvs_packed == 0:
                num_uvs_packed = 2 if has_tex2 else 1
        else:
            num_uvs_packed = 0

        num_tris, num_verts, num_morph = struct.unpack("<III", f.read(12))
        print(f"   [GEO] flags={hex(flags)} tris={num_tris} verts={num_verts} uvsets={num_uvs_packed}")

        has_colors  = bool(flags & cls.FLAG_COLORS)
        has_normals = bool(flags & cls.FLAG_NORMALS)

        # Pre-lit vertex colours (RGBA, 4 bytes each) — MUST be read before UVs
        if has_colors:
            f.read(num_verts * 4)

        # UV sets — read and store ALL sets (Set 0, Set 1, etc.)
        num_uv_sets = num_uvs_packed
        all_uv_sets = []
        for i in range(num_uv_sets):
            data = f.read(num_verts * 8)
            set_uvs = np.frombuffer(data, dtype=np.float32).reshape(num_verts, 2).copy()
            # SA coordinates: (0,0) is top-left. OpenGL: (0,0) is bottom-left.
            set_uvs[:, 1] = 1.0 - set_uvs[:, 1]
            all_uv_sets.append(set_uvs)

        # Fallback if no UVs found but flags said there were
        if num_uv_sets == 0:
            all_uv_sets.append(np.zeros((num_verts, 2), dtype=np.float32))

        # Triangles  [v2 u16, v1 u16, matId u16, v3 u16]
        raw_quad = np.frombuffer(f.read(num_tris * 8), dtype=np.uint16).reshape(num_tris, 4)
        all_faces  = np.column_stack([raw_quad[:, 1], raw_quad[:, 0], raw_quad[:, 3]]).astype(np.int32)
        face_matid = raw_quad[:, 2].astype(np.int32)

        # Morph targets
        verts = np.zeros((num_verts, 3), dtype=np.float32)
        norms = np.zeros((num_verts, 3), dtype=np.float32)
        for _ in range(num_morph):
            f.read(16)   # bounding sphere
            hv = struct.unpack("<I", f.read(4))[0]
            hn = struct.unpack("<I", f.read(4))[0]
            if hv:
                verts = np.frombuffer(f.read(num_verts * 12), dtype=np.float32).reshape(num_verts, 3).copy()
            if hn:
                norms = np.frombuffer(f.read(num_verts * 12), dtype=np.float32).reshape(num_verts, 3).copy()

        # ---------- Material List ----------
        mat_names = []   # index → texture name string
        binmesh_groups = None   # list of (mat_idx, face_indices_array)

        while f.tell() < geo_end - 11:
            ct, cs, cv = cls.read_chunk_header(f)
            chunk_end = f.tell() + cs
            if cs == 0:
                f.seek(chunk_end); continue

            if ct == cls.CHUNK_MATERIAL_LIST:
                mat_names = cls._read_material_list(f, cs)
                print(f"   [MAT LIST] {len(mat_names)} materiales: {mat_names}")

            elif ct == cls.CHUNK_EXTENSION:
                binmesh_groups = cls._read_extension_binmesh(f, cs)
                if binmesh_groups:
                    print(f"   [BINMESH] {len(binmesh_groups)} grupos de material")

            f.seek(chunk_end)

        # ---------- Build sub-meshes ----------
        sub_meshes = []

        if binmesh_groups:
            # Use BinMesh groups (most accurate for GTA SA)
            for mat_idx, idx_array in binmesh_groups:
                tri_faces = idx_array.reshape(-1, 3)
                tri_faces = np.clip(tri_faces, 0, num_verts - 1)
                mat = mat_names[mat_idx] if mat_idx < len(mat_names) else ""
                sub_meshes.append({
                    "vertices":  verts,
                    "uv_sets":   all_uv_sets,
                    "normals":   norms,
                    "faces":     tri_faces.astype(np.int32),
                    "materials": [mat],
                })
        else:
            # Fallback: group faces by per-face material ID
            mat_ids = np.unique(face_matid)
            for mid in mat_ids:
                mask = face_matid == mid
                sub_faces = all_faces[mask]
                sub_faces = np.clip(sub_faces, 0, num_verts - 1)
                mat = mat_names[int(mid)] if int(mid) < len(mat_names) else ""
                sub_meshes.append({
                    "vertices":  verts,
                    "uv_sets":   all_uv_sets,
                    "normals":   norms,
                    "faces":     sub_faces.astype(np.int32),
                    "materials": [mat],
                })


        if not sub_meshes:
            # Degenerate: single mesh, no material info
            sub_meshes.append({
                "vertices":  verts,
                "uvs":       uvs,
                "normals":   norms,
                "faces":     np.clip(all_faces, 0, num_verts-1).astype(np.int32),
                "materials": [mat_names[0]] if mat_names else [],
            })

        return sub_meshes

    @classmethod
    def _read_material_list(cls, f, size):
        """Returns list[str]: texture name for each material index."""
        end = f.tell() + size
        mat_names = []

        # Struct: num_mats + index array
        cls.read_chunk_header(f)
        num_mats = struct.unpack("<I", f.read(4))[0]
        mat_indices = list(struct.unpack(f"<{num_mats}i", f.read(num_mats * 4)))

        # Read material chunks
        for mi in range(num_mats):
            if mat_indices[mi] != -1:
                # Material instance → reuse name from parent
                parent = mat_indices[mi]
                mat_names.append(mat_names[parent] if parent < len(mat_names) else "")
                continue

            ct, cs, cv = cls.read_chunk_header(f)
            if ct != cls.CHUNK_MATERIAL:
                f.seek(cs, 1)
                mat_names.append("")
                continue

            mat_end = f.tell() + cs
            tex_name = ""

            while f.tell() < mat_end - 11:
                mt, ms, mv = cls.read_chunk_header(f)
                mend = f.tell() + ms
                if ms == 0:
                    continue

                if mt == cls.CHUNK_TEXTURE and tex_name == "":
                    # Inside TEXTURE: Struct → TexName(string) → MaskName(string) → Extension
                    inner_end = f.tell() + ms
                    while f.tell() < inner_end - 11:
                        tt, ts, tv = cls.read_chunk_header(f)
                        tce = f.tell() + ts
                        if tt == cls.CHUNK_STRUCT:
                            f.seek(ts, 1)  # skip texture flags
                        elif tt == cls.CHUNK_STRING and ts > 0 and tex_name == "":
                            raw = f.read(ts)
                            tex_name = raw.split(b"\x00")[0].decode("utf-8", "ignore").strip()
                        else:
                            f.seek(tce)
                    f.seek(inner_end)
                else:
                    f.seek(mend)

            mat_names.append(tex_name)
            f.seek(mat_end)

        return mat_names

    @classmethod
    def _read_extension_binmesh(cls, f, size):
        """
        Scans Extension chunk for BinMesh PLG (0x050E).
        Returns list of (material_index, np.array of flat vertex indices) or None.
        """
        end = f.tell() + size
        groups = None

        while f.tell() < end - 11:
            ct, cs, cv = cls.read_chunk_header(f)
            chunk_end = f.tell() + cs
            if cs == 0:
                f.seek(chunk_end); continue

            if ct == cls.CHUNK_BINMESH_PLG:
                groups = cls._parse_binmesh(f, cs)
                f.seek(chunk_end)
                break
            else:
                f.seek(chunk_end)

        return groups

    @classmethod
    def _parse_binmesh(cls, f, chunk_size):
        """
        BinMesh format (Bin Mesh PLG  0x050E):
          flags        u32  (0=tri-list, 1=tri-strip)
          numMeshes    u32
          totalIndices u32
          for each mesh:
            numIndices  u32
            materialIdx u32
            indices     u16[] OR u32[]   ← size auto-detected like DragonFF

        DragonFF detects 16 vs 32-bit indices:
          if (12 + mesh_count*8 + total_indices*2) >= chunk_size → 16-bit (opengl/PS2)
          else → 32-bit (PC D3D)
        """
        start = f.tell()
        flags        = struct.unpack("<I", f.read(4))[0]
        num_meshes   = struct.unpack("<I", f.read(4))[0]
        total_idx    = struct.unpack("<I", f.read(4))[0]
        is_strip     = bool(flags & 1)

        # Auto-detect index width (same logic as DragonFF)
        calculated_size_16bit = 12 + num_meshes * 8 + total_idx * 2
        use_16bit = (calculated_size_16bit >= chunk_size)
        idx_fmt   = "<H" if use_16bit else "<I"
        idx_bytes = 2    if use_16bit else 4
        print(f"   [BINMESH] strip={is_strip} meshes={num_meshes} totalIdx={total_idx} idx={'16bit' if use_16bit else '32bit'}")

        groups = []
        for _ in range(num_meshes):
            num_idx = struct.unpack("<I", f.read(4))[0]
            mat_idx = struct.unpack("<I", f.read(4))[0]
            indices = list(struct.unpack(f"<{num_idx}{idx_fmt[1]}", f.read(num_idx * idx_bytes)))

            if is_strip:
                # DragonFF strip winding: even→(prev[1],prev[0],v)  odd→(prev[0],prev[1],v)
                tris = []
                prev = []
                for j, v in enumerate(indices):
                    if len(prev) < 2:
                        prev.append(v)
                        continue
                    if j % 2 == 0:
                        tris.extend([prev[1], prev[0], v])
                    else:
                        tris.extend([prev[0], prev[1], v])
                    prev[0] = prev[1]
                    prev[1] = v
                indices = tris
            else:
                # Tri-list: DragonFF reads in groups of 3 as (b, a, mat, c)
                # meaning face order is [indices[1], indices[0], indices[2]]
                out = []
                for i in range(0, len(indices) - 2, 3):
                    out.extend([indices[i+1], indices[i], indices[i+2]])
                indices = out

            groups.append((int(mat_idx), np.array(indices, dtype=np.int32)))

        return groups


    # ------------------------------------------------------------------ #
    #  TXD                                                                 #
    # ------------------------------------------------------------------ #
    @classmethod
    def parse_txd(cls, path):
        textures = {}
        with open(path, "rb") as f:
            ct, cs, cv = cls.read_chunk_header(f)
            if ct != cls.CHUNK_TEXTURE_DICTIONARY:
                return {}
            dict_end = f.tell() + cs

            # Struct: num_textures(H) device(H)
            cls.read_chunk_header(f)
            num_tex = struct.unpack("<H", f.read(2))[0]
            f.read(2)

            for _ in range(num_tex):
                ct2, cs2, _ = cls.read_chunk_header(f)
                chunk_end = f.tell() + cs2
                if ct2 == cls.CHUNK_TEXNATIVE:
                    chunk_start = f.tell() - 12
                    f.seek(chunk_start)
                    raw_chunk = f.read(cs2 + 12)
                    f.seek(chunk_start + 12)
                    
                    name, img = cls._parse_tex_native(f, cs2)
                    if name:
                        img.info["txd_raw_chunk"] = raw_chunk
                        textures[name.lower()] = img
                f.seek(chunk_end)
        return textures

    @classmethod
    def _parse_tex_native(cls, f, size):
        end_chunk = f.tell() + size

        cls.read_chunk_header(f)  # struct sub-chunk header

        platform    = struct.unpack("<I", f.read(4))[0]  # 8 = PC/D3D9
        filter_addr = struct.unpack("<I", f.read(4))[0]
        name  = f.read(32).split(b"\x00")[0].decode("utf-8", "ignore")
        mask  = f.read(32).split(b"\x00")[0].decode("utf-8", "ignore")

        raster_format = struct.unpack("<I", f.read(4))[0]
        d3d_format    = struct.unpack("<I", f.read(4))[0]
        width         = struct.unpack("<H", f.read(2))[0]
        height        = struct.unpack("<H", f.read(2))[0]
        depth         = struct.unpack("<B", f.read(1))[0]
        num_mip       = struct.unpack("<B", f.read(1))[0]
        raster_type   = struct.unpack("<B", f.read(1))[0]
        d3d_flags     = struct.unpack("<B", f.read(1))[0]

        is_pal4 = bool(raster_format & 0x2000)
        is_pal8 = bool(raster_format & 0x4000)

        palette = None
        if is_pal8:
            bgra = np.frombuffer(f.read(256 * 4), dtype=np.uint8).reshape(256, 4)
            palette = bgra[:, [2, 1, 0, 3]].copy()
        elif is_pal4:
            bgra = np.frombuffer(f.read(16 * 4), dtype=np.uint8).reshape(16, 4)
            palette = bgra[:, [2, 1, 0, 3]].copy()

        mip_size   = struct.unpack("<I", f.read(4))[0]
        pixel_data = f.read(mip_size)
        f.seek(end_chunk)

        fourcc_raw = struct.pack("<I", d3d_format).decode("ascii", "ignore").strip("\x00")
        fourcc = fourcc_raw
        if not fourcc and not is_pal8 and not is_pal4:
            dxt1_size = ((width + 3) // 4) * ((height + 3) // 4) * 8
            dxt5_size = ((width + 3) // 4) * ((height + 3) // 4) * 16
            if mip_size == dxt1_size:
                fourcc = "DXT1"
            elif mip_size == dxt5_size:
                fourcc = "DXT3"

        print(f"   [TXD] '{name}'  fmt={fourcc_raw!r} -> {fourcc!r} ({hex(d3d_format)})  {width}x{height}  depth={depth}  pal8={is_pal8}")

        img = None
        
        # Save exact metadata properties for inheritance
        meta = {
            "platform": platform,
            "filter_addr": filter_addr,
            "d3d_format": d3d_format,
            "raster_format": raster_format,
            "depth": depth,
            "fourcc": fourcc.strip('\x00'),
            "d3d_flags": d3d_flags,
            "raster_type": raster_type,
            "num_mip": num_mip
        }
        
        try:
            if "DXT1" in fourcc:
                img = cls._decompress_dxt(pixel_data, width, height, "DXT1")
            elif "DXT3" in fourcc:
                img = cls._decompress_dxt(pixel_data, width, height, "DXT3")
            elif "DXT5" in fourcc:
                img = cls._decompress_dxt(pixel_data, width, height, "DXT5")
            elif is_pal8 and palette is not None:
                idx = np.frombuffer(pixel_data, dtype=np.uint8)[:width*height].reshape(height, width)
                img = Image.fromarray(palette[idx], "RGBA")
            elif is_pal4 and palette is not None:
                raw_bytes = np.frombuffer(pixel_data, dtype=np.uint8)
                idx = np.empty(raw_bytes.size * 2, dtype=np.uint8)
                idx[0::2] = raw_bytes & 0x0F
                idx[1::2] = raw_bytes >> 4
                idx = idx[:width*height].reshape(height, width)
                img = Image.fromarray(palette[idx], "RGBA")
            elif depth == 32:
                expected = width * height * 4
                padded = pixel_data + b"\x00" * max(0, expected - len(pixel_data))
                raw = np.frombuffer(padded[:expected], dtype=np.uint8).reshape(height, width, 4)
                img = Image.fromarray(raw[:, :, [2, 1, 0, 3]], "RGBA")   # BGRA → RGBA
            elif depth == 24:
                row = (width * 3 + 3) & ~3
                expected = row * height
                padded = pixel_data + b"\x00" * max(0, expected - len(pixel_data))
                raw = np.frombuffer(padded[:expected], dtype=np.uint8).reshape(height, row)[:, :width*3].reshape(height, width, 3)
                img = Image.fromarray(raw[:, :, [2, 1, 0]], "RGB")
            elif depth == 16:
                expected = width * height * 2
                padded = pixel_data + b"\x00" * max(0, expected - len(pixel_data))
                r16 = np.frombuffer(padded[:expected], dtype=np.uint16).reshape(height, width)
                r = ((r16 >> 11) & 0x1F) * 255 // 31
                g = ((r16 >>  5) & 0x3F) * 255 // 63
                b = ( r16        & 0x1F) * 255 // 31
                img = Image.fromarray(np.stack([r, g, b], -1).astype(np.uint8), "RGB")
        except Exception as e:
            print(f"   [WARN] Error decoding '{name}': {e}")

        if img is None:
            print(f"   [WARN] No handler for '{name}', usando placeholder")
            img = Image.new("RGBA", (max(1, width), max(1, height)), (128, 128, 128, 255))

        for k, v in meta.items():
            img.info[k] = v

        return name, img

    @staticmethod
    def _make_chunk(chunk_id, data, rw_version=0x1803FFFF):
        """Creates a RenderWare chunk with standard header."""
        size = len(data)
        header = struct.pack("<III", chunk_id, size, rw_version)
        return header + data

    @staticmethod
    def _compress_dxt1(img: Image.Image, is_dxt5=False) -> bytes:
        import numpy as np
        arr = np.array(img.convert("RGBA")).astype(np.int32)
        h, w = arr.shape[:2]
        bw, bh = (w + 3) // 4, (h + 3) // 4
        padded = np.zeros((bh * 4, bw * 4, 4), dtype=np.int32)
        padded[:h, :w] = arr

        c0, c1, c2 = padded.strides
        blocks = np.lib.stride_tricks.as_strided(
            padded, 
            shape=(bh, bw, 4, 4, 4), 
            strides=(c0*4, c1*4, c0, c1, c2)
        ).reshape(-1, 16, 4)

        c_max = blocks[:, :, :3].max(axis=1)
        c_min = blocks[:, :, :3].min(axis=1)

        def to_565(c):
            return ((c[:, 0] >> 3) << 11) | ((c[:, 1] >> 2) << 5) | (c[:, 2] >> 3)

        max_565 = to_565(c_max).astype(np.uint16)
        min_565 = to_565(c_min).astype(np.uint16)

        swap = max_565 <= min_565
        max_565[swap], min_565[swap] = min_565[swap], max_565[swap]
        eq = max_565 == min_565
        max_565[eq] = np.clip(max_565[eq] + 1, 0, 65535)

        def from_565(c):
            r = ((c >> 11) & 0x1F); r = (r << 3) | (r >> 2)
            g = ((c >> 5) & 0x3F);  g = (g << 2) | (g >> 4)
            b = (c & 0x1F);         b = (b << 3) | (b >> 2)
            return np.stack([r, g, b], axis=-1)

        c0_rgb = from_565(max_565)
        c1_rgb = from_565(min_565)
        
        c_all = np.zeros((len(blocks), 4, 3), dtype=np.int32)
        c_all[:, 0] = c0_rgb
        c_all[:, 1] = c1_rgb
        c_all[:, 2] = (2 * c0_rgb + c1_rgb) // 3
        c_all[:, 3] = (c0_rgb + 2 * c1_rgb) // 3

        diff = blocks[:, :, None, :3] - c_all[:, None, :, :]
        dist = (diff * diff).sum(axis=-1)
        best_idx = dist.argmin(axis=-1).astype(np.uint32)

        indices = np.zeros(len(blocks), dtype=np.uint32)
        for i in range(16):
            indices |= (best_idx[:, i] << (i * 2))

        block_size = 16 if is_dxt5 else 8
        out = np.zeros((len(blocks), block_size), dtype=np.uint8)
        
        c_offset = 8 if is_dxt5 else 0
        if is_dxt5:
            # solid opaque alpha
            out[:, 0] = 255
            out[:, 1] = 0
            # Next 6 bytes are 0 (indices picking 255)

        out[:, c_offset + 0] = max_565 & 0xFF
        out[:, c_offset + 1] = (max_565 >> 8) & 0xFF
        out[:, c_offset + 2] = min_565 & 0xFF
        out[:, c_offset + 3] = (min_565 >> 8) & 0xFF
        out[:, c_offset + 4] = indices & 0xFF
        out[:, c_offset + 5] = (indices >> 8) & 0xFF
        out[:, c_offset + 6] = (indices >> 16) & 0xFF
        out[:, c_offset + 7] = (indices >> 24) & 0xFF

        return out.tobytes()

    @classmethod
    def write_txd(cls, path, textures_list, rw_version=0x1803FFFF):
        """
        Writes a TXD file inheriting properties (DXT compression etc.)
        """
        tex_chunks = b""
        for tex in textures_list:
            img = tex['img']
            
            # 1. If untouched, write original chunk
            if "txd_raw_chunk" in img.info:
                tex_chunks += img.info["txd_raw_chunk"]
                continue
                
            # 2. If replaced, encode with inherited properties
            meta_cache = img.info.copy()
            
            img = img.convert("RGBA")
            width, height = img.size
            if width == 0 or height == 0:
                width, height = 4, 4
                img = img.resize((4, 4))
                
            platform = meta_cache.get("platform", 8)
            filter_flags = meta_cache.get("filter_addr", 0x1102)
            d3d_format = meta_cache.get("d3d_format", 21) # 21 = A8R8G8B8
            raster_format = meta_cache.get("raster_format", 0x0500) # 0x0500 = 8888
            depth = meta_cache.get("depth", 32)
            fourcc = meta_cache.get("fourcc", "")
            d3d_flags = meta_cache.get("d3d_flags", 0)
            raster_type = meta_cache.get("raster_type", 4)

            # If it's a completely new texture (no meta), ensure it's not 1555 which looks purple
            if not "raster_format" in meta_cache:
                raster_format = 0x0500
                d3d_format = 21
                depth = 32

            name_bytes = tex['name'].encode("utf-8", "ignore")
            name = name_bytes.ljust(32, b'\x00')[:32]
            mask = name_bytes.ljust(32, b'\x00')[:32]
            
            # Optionally generate mipmaps if num_mip > 1
            num_mip = meta_cache.get("num_mip", 1)
            # Currently we only generate 1 level in the array, so we must set num_mip to 1 
            # to prevent Magic.TXD from reading past EOF if it expects more data.
            # But the user asked to inherit the setting! So we will output the DXT data 
            # but we need to generate mipmaps if num_mip > 1.
            
            pixel_bytes = b""
            if num_mip > 1:
                # Need to build mipmap bytechain
                mw, mh = width, height
                m_img = img
                for mip in range(num_mip):
                    if "DXT1" in fourcc:
                        pixel_bytes += cls._compress_dxt1(m_img, False)
                    elif "DXT5" in fourcc or "DXT3" in fourcc:
                        pixel_bytes += cls._compress_dxt1(m_img, True)
                    else:
                        m_arr = np.array(m_img.convert("RGBA"), dtype=np.uint8)[:, :, [2, 1, 0, 3]]
                        pixel_bytes += m_arr.tobytes()
                    
                    if mw > 1 or mh > 1:
                        mw, mh = max(1, mw // 2), max(1, mh // 2)
                        # Avoid 0 size
                        m_img = m_img.resize((mw, mh), Image.Resampling.LANCZOS)
            else:
                if "DXT1" in fourcc:
                    pixel_bytes = cls._compress_dxt1(img, False)
                elif "DXT5" in fourcc or "DXT3" in fourcc:
                    pixel_bytes = cls._compress_dxt1(img, True)
                else:
                    raw_rgba = np.array(img, dtype=np.uint8)
                    bgra = raw_rgba[:, :, [2, 1, 0, 3]].copy()
                    pixel_bytes = bgra.tobytes()
            
            struct_data = struct.pack("<II32s32sIIHHBBBB",
                platform, filter_flags, name, mask,
                raster_format, d3d_format, width, height, depth, num_mip, raster_type, d3d_flags
            )
            
            mip_size = len(pixel_bytes)
            struct_data += struct.pack("<I", mip_size) + pixel_bytes
            
            tex_struct_chunk = cls._make_chunk(cls.CHUNK_STRUCT, struct_data, rw_version)
            tex_ext_chunk = cls._make_chunk(cls.CHUNK_EXTENSION, b"", rw_version)
            
            tex_native_data = tex_struct_chunk + tex_ext_chunk
            tex_chunks += cls._make_chunk(cls.CHUNK_TEXNATIVE, tex_native_data, rw_version)
            
        dict_struct = struct.pack("<HH", len(textures_list), 9) # 9 = device ID PC/D3D9
        dict_struct_chunk = cls._make_chunk(cls.CHUNK_STRUCT, dict_struct, rw_version)
        dict_ext_chunk = cls._make_chunk(cls.CHUNK_EXTENSION, b"", rw_version)
        
        dict_data = dict_struct_chunk + tex_chunks + dict_ext_chunk
        full_txd = cls._make_chunk(cls.CHUNK_TEXTURE_DICTIONARY, dict_data, rw_version)
        
        with open(path, "wb") as f:
            f.write(full_txd)

    # ------------------------------------------------------------------ #
    #  DXT Decompressor                                                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decompress_dxt(data: bytes, width: int, height: int, fmt: str) -> Image.Image:
        """
        Fast vectorized DXT decompressor using NumPy.
        Significantly faster than nested Python loops.
        """
        bw = (width + 3) // 4
        bh = (height + 3) // 4
        
        # Output RGBA buffer
        out = np.zeros((bh * 4, bw * 4, 4), dtype=np.uint8)
        
        # Block size in bytes
        block_size = 8 if fmt == "DXT1" else 16
        if len(data) < bh * bw * block_size:
            # Padding if data is truncated
            data = data.ljust(bh * bw * block_size, b"\x00")
            
        data_arr = np.frombuffer(data, dtype=np.uint8)
        
        # --- Handle Alpha ---
        alphas = np.full((bh * bw, 16), 255, dtype=np.uint8)
        color_offset = 0
        
        if fmt == "DXT3":
            # DXT3: 64 bits of alpha (4 bits per pixel)
            alpha_data = data_arr.reshape(-1, 16)[:, :8]
            # Unpack 4-bit alphas
            a_low = (alpha_data & 0x0F) * 17
            a_high = (alpha_data >> 4) * 17
            alphas = np.stack([a_low, a_high], axis=2).reshape(-1, 16)
            color_offset = 8
            
        elif fmt == "DXT5":
            # DXT5: 64 bits of alpha (a0, a1, 3-bit indices)
            a0 = data_arr[0::16].astype(np.int32)
            a1 = data_arr[1::16].astype(np.int32)
            
            # 48 bits of indices
            # We use a simpler approach for DXT5 alpha for now if needed, 
            # but let's try to vectorize it too
            a_blocks = data_arr.reshape(-1, 16)
            a0 = a_blocks[:, 0].astype(np.uint8)
            a1 = a_blocks[:, 1].astype(np.uint8)
            
            # Bits 2..7 of the 8-byte alpha block
            a_bits = a_blocks[:, 2:8].astype(np.uint64)
            # Combine into 48-bit integer per block
            a_indices_raw = np.zeros(len(a_blocks), dtype=np.uint64)
            for i in range(6):
                a_indices_raw |= a_bits[:, i].astype(np.uint64) << (8 * i)
            
            # Interpolate alpha values
            # a_table: (num_blocks, 8)
            a_table = np.zeros((len(a_blocks), 8), dtype=np.uint8)
            a_table[:, 0] = a0
            a_table[:, 1] = a1
            
            mask = a0 > a1
            # Case a0 > a1
            for i in range(2, 8):
                a_table[mask, i] = ((8 - i) * a0[mask] + (i - 1) * a1[mask]) // 7
            # Case a0 <= a1
            for i in range(2, 6):
                a_table[~mask, i] = ((6 - i) * a0[~mask] + (i - 1) * a1[~mask]) // 5
            a_table[~mask, 6] = 0
            a_table[~mask, 7] = 255
            
            # Extract 3-bit indices
            for i in range(16):
                idx = (a_indices_raw >> (3 * i)) & 7
                alphas[:, i] = a_table[np.arange(len(a_blocks)), idx.astype(np.int32)]
            
            color_offset = 8

        # --- Handle Color ---
        # Color data starts at color_offset within each 8 or 16 byte block
        c_blocks = data_arr.reshape(-1, block_size)[:, color_offset:]
        
        # c0, c1 (16-bit 565)
        c0r = c_blocks[:, 0].astype(np.uint16) | (c_blocks[:, 1].astype(np.uint16) << 8)
        c1r = c_blocks[:, 2].astype(np.uint16) | (c_blocks[:, 3].astype(np.uint16) << 8)
        
        # Unpack 565 to RGB
        def unpack_565(c):
            r = ((c >> 11) & 0x1F); r = (r << 3) | (r >> 2)
            g = ((c >>  5) & 0x3F); g = (g << 2) | (g >> 4)
            b = ( c        & 0x1F); b = (b << 3) | (b >> 2)
            return np.stack([r, g, b], axis=-1).astype(np.int32)
            
        colors0 = unpack_565(c0r)
        colors1 = unpack_565(c1r)
        
        # Interpolate
        num_blocks = len(c0r)
        ct = np.zeros((num_blocks, 4, 3), dtype=np.int32)
        ct[:, 0] = colors0
        ct[:, 1] = colors1
        
        if fmt == "DXT1":
            mask = c0r > c1r
            ct[mask, 2] = (2 * colors0[mask] + colors1[mask]) // 3
            ct[mask, 3] = (colors0[mask] + 2 * colors1[mask]) // 3
            ct[~mask, 2] = (colors0[~mask] + colors1[~mask]) // 2
            ct[~mask, 3] = 0 # Black
        else:
            ct[:, 2] = (2 * colors0 + colors1) // 3
            ct[:, 3] = (colors0 + 2 * colors1) // 3
            
        # Color indices (32 bits = 16 pixels * 2 bits)
        c_indices_raw = (
            c_blocks[:, 4].astype(np.uint32) | 
            (c_blocks[:, 5].astype(np.uint32) << 8) |
            (c_blocks[:, 6].astype(np.uint32) << 16) |
            (c_blocks[:, 7].astype(np.uint32) << 24)
        )
        
        # Map pixels
        block_idx = np.arange(num_blocks)
        for i in range(16):
            idx = (c_indices_raw >> (2 * i)) & 3
            # Pixel location in output image
            px = (block_idx % bw) * 4 + (i % 4)
            py = (block_idx // bw) * 4 + (i // 4)
            
            pixel_colors = ct[block_idx, idx]
            out[py, px, :3] = pixel_colors
            
            if fmt == "DXT1":
                # DXT1 alpha: if c0 <= c1 and index is 3, alpha is 0
                alpha = np.full(num_blocks, 255, dtype=np.uint8)
                alpha[(~mask) & (idx == 3)] = 0
                out[py, px, 3] = alpha
            else:
                out[py, px, 3] = alphas[:, i]
                
        # Trim to actual size and return Image
        return Image.fromarray(out[:height, :width], "RGBA")
