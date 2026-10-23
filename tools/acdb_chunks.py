import sys, struct
d = open(sys.argv[1], 'rb').read()
assert d[:4] == b'ACDB'
_, total = struct.unpack_from('<II', d, 4)
off = 12
while off + 8 <= len(d):
    tag = d[off:off+4]
    size, = struct.unpack_from('<I', d, off+4)
    print(f'{off:08x} {tag.decode("latin1"):4} size={size:#x} ({size})')
    off += 8 + size
