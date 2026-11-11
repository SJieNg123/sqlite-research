import sqlite3, struct, sys, collections
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
roots = con.execute("select type,name,tbl_name,rootpage from sqlite_schema where rootpage>0").fetchall()
con.close()
PS = 4096
f = open(db, "rb")
def hdr(pg):
    f.seek((pg-1)*PS); b = f.read(PS)
    off = 100 if pg == 1 else 0
    t = b[off]
    ncell = struct.unpack(">H", b[off+3:off+5])[0]
    right = struct.unpack(">I", b[off+8:off+12])[0] if t in (2,5) else None
    return t, ncell, right, b, off
def children(pg):
    t, n, right, b, off = hdr(pg)
    if t not in (2,5): return []
    ptrs = [struct.unpack(">H", b[off+12+2*i:off+14+2*i])[0] for i in range(n)]
    return [struct.unpack(">I", b[p:p+4])[0] for p in ptrs] + [right]
for typ, name, tbl, root in roots:
    levels = collections.Counter(); frontier = [root]; depth = 0
    while frontier:
        depth += 1
        kinds = collections.Counter(hdr(p)[0] for p in frontier)
        levels[depth] = (len(frontier), dict(kinds))
        frontier = [c for p in frontier for c in children(p)]
    print(f"{typ:6} {name:28} root={root:6} depth={depth} levels={dict(levels)}")
