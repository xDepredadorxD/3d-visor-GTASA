import struct
import copy
import numpy as np

def make_chunk(chunk_id, data, rw_version=0x1803FFFF):
    size = len(data)
    header = struct.pack("<III", chunk_id, size, rw_version)
    return header + data

def make_txd(path, textures):
    rw_version = 0x1803FFFF
    
    tex_chunks = b""
    for tex in textures:
        img = tex['img'].convert("RGBA")
        width, height = img.size
        # Resize to power of two if needed, but assuming it's valid for now
        
        # BGRA 32 bit format
        platform = 8
        filter_flags = 0x1102
        name = tex['name'].encode("utf-8").ljust(32, b'\x00')[:32]
        mask = tex['name'].encode("utf-8").ljust(32, b'\x00')[:32]
        
        raster_format = 0x0150 # Some generic raw RGBA format flag
        d3d_format = 21 # D3DFMT_A8R8G8B8
        depth = 32
        num_mip = 1
        raster_type = 4
        d3d_flags = 0
        
        struct_data = struct.pack("<II32s32sIIHHBBBB",
            platform, filter_flags, name, mask,
            raster_format, d3d_format, width, height, depth, num_mip, raster_type, d3d_flags
        )
        
        # Pixel data
        raw_rgba = np.array(img, dtype=np.uint8)
        # Convert RGBA to BGRA
        bgra = raw_rgba[:, :, [2, 1, 0, 3]].copy()
        pixel_bytes = bgra.tobytes()
        
        mip_size = len(pixel_bytes)
        struct_data += struct.pack("<I", mip_size) + pixel_bytes
        
        tex_struct_chunk = make_chunk(0x01, struct_data, rw_version)
        tex_ext_chunk = make_chunk(0x03, b"", rw_version)
        
        tex_native_data = tex_struct_chunk + tex_ext_chunk
        tex_chunks += make_chunk(0x15, tex_native_data, rw_version)
        
    # Dictionary struct
    dict_struct = struct.pack("<HH", len(textures), 9) # 9 = device ID?
    dict_struct_chunk = make_chunk(0x01, dict_struct, rw_version)
    
    dict_ext_chunk = make_chunk(0x03, b"", rw_version)
    
    dict_data = dict_struct_chunk + tex_chunks + dict_ext_chunk
    full_txd = make_chunk(0x16, dict_data, rw_version)
    
    with open(path, "wb") as f:
        f.write(full_txd)

# Test it
from PIL import Image
class Test:
    pass

textures = [{'name':'test', 'img': Image.new("RGBA", (64, 64), (255, 0, 0, 255))}]
make_txd("test.txd", textures)
print("Done writing.")
