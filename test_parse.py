from rw_parser import RWParser

textures = RWParser.parse_txd("test.txd")
print(textures)
if 'test' in textures:
    img = textures['test']
    print(img.size, img.mode)
