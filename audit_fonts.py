#!/usr/bin/env python3
"""检测 CFF/OTF 字体是否结构损坏（会导致中文渲染成"另一个真实汉字"）。

原理：损坏字体的 TopDICT 里 charset/CharStrings/FDArray 偏移挤在一起且小到不合理，
而 CFF 表本身有几十 MB。按规范解析的引擎（Flutter/WebKit）读到错位数据，
渲染出相邻字形——这就是"部分对部分错"的乱码成因。

用法:
    python3 audit_fonts.py [font files...]
    python3 audit_fonts.py          # 检测 ~/Library/Fonts/ 下所有字体

退出码: 0 = 全部正常, 1 = 发现损坏
"""
import struct
import sys
from pathlib import Path

# CharStrings 表在 CFF 内的最小合理位置。
# 一个含上万字形的 CFF，光是 charset + 若干索引就远超此值；
# 若 TopDICT 声称的偏移小于它，说明头部偏移未指向有效数据。
MIN_CHARSTRINGS_OFFSET = 1024


def read_index(d, o):
    """读一个 CFF INDEX 结构，返回 (items, 结束位置)。"""
    cnt = struct.unpack('>H', d[o:o + 2])[0]
    if cnt == 0:
        return [], o + 2
    off_size = d[o + 2]
    p = o + 3
    offs = []
    for _ in range(cnt + 1):
        v = 0
        for _ in range(off_size):
            v = (v << 8) | d[p]
            p += 1
        offs.append(v)
    base = p - 1
    return [d[base + offs[i]:base + offs[i + 1]] for i in range(cnt)], base + offs[-1]


def table_dir(d, sfnt_off):
    """解析 sfnt 容器（OTF 单体或 TTC 内某个字体）的表目录。"""
    num = struct.unpack('>H', d[sfnt_off + 4:sfnt_off + 6])[0]
    t = {}
    for i in range(num):
        off = sfnt_off + 12 + i * 16
        t[d[off:off + 4].decode('latin1')] = struct.unpack('>II', d[off + 8:off + 16])
    return t


def parse_topdict(tb):
    """从 TopDICT 数据里提取 charset / CharStrings / FDArray 偏移。"""
    offsets = {}
    i, ops = 0, []
    while i < len(tb):
        b = tb[i]
        if b <= 21:
            if b == 12:
                # 12 36 = FDArray
                if tb[i + 1] == 36 and ops:
                    offsets['fdarray'] = ops[-1]
                i += 2
                continue
            if b == 15 and ops:          # charset
                offsets['charset'] = ops[-1]
            if b == 17 and ops:          # CharStrings
                offsets['charstrings'] = ops[-1]
            ops = []
            i += 1
            continue
        elif b == 28:
            ops.append(struct.unpack('>H', tb[i + 1:i + 3])[0]); i += 3
        elif b == 29:
            ops.append(struct.unpack('>i', tb[i + 1:i + 5])[0]); i += 5
        elif b == 247:
            ops.append(tb[i + 1] - 108); i += 2
        elif b == 251:
            ops.append(tb[i + 1] - 113); i += 2
        elif 32 <= b <= 246:
            ops.append(b - 139); i += 1
        else:
            i += 1
    return offsets


def audit(path):
    d = open(path, 'rb').read()
    magic = d[:4]
    note = ""

    if magic == b'ttcf':
        num_fonts = struct.unpack('>I', d[8:12])[0]
        sfnt = struct.unpack('>I', d[12:16])[0]
        t = table_dir(d, sfnt)
        note = f"(ttcf 集合，{num_fonts} 个字体，检第 1 个)"
        if 'CFF ' not in t:
            print(f"{path} {note}\n  无 CFF 表（glyf/TrueType 轮廓）—— 正常形态\n  ==> OK\n")
            return False
    elif magic == b'OTTO':
        t = table_dir(d, 0)
        if 'CFF ' not in t:
            print(f"{path}\n  无 CFF 表 —— 跳过\n")
            return None
    elif magic == b'\x00\x01\x00\x00':
        print(f"{path}\n  普通 TrueType（.ttf）—— 无 CFF 表，不适用本检测\n  ==> OK\n")
        return False
    else:
        print(f"{path}\n  无法识别 (magic={magic})\n")
        return None

    cff, cff_len = t['CFF ']
    o = cff + d[cff + 2]
    _, o = read_index(d, o)          # Name index
    top, o = read_index(d, o)        # TopDICT index
    strs, o = read_index(d, o)       # String index

    off = parse_topdict(top[0]) if top else {}
    cs, chs, fd = off.get('charset'), off.get('charstrings'), off.get('fdarray')

    print(f"{path} {note}")
    print(f"  CFF 表: offset={cff}, length={cff_len} ({cff_len/1048576:.1f} MB)")
    print(f"  String Index: {len(strs)} 项")
    print(f"  TopDICT 偏移: charset={cs}, CharStrings={chs}, FDArray={fd}")

    problems = []
    if chs is None:
        problems.append("TopDICT 缺少 CharStrings 偏移")
    elif chs < MIN_CHARSTRINGS_OFFSET:
        # 唯一可靠的不变量：上万字形的 CFF，其 CharStrings 偏移必然远大于此。
        # （官方 CID 字体的 FDArray 大于 CharStrings、偏移比例悬殊都是正常的，
        #   不能拿这两条当判据——会误伤 Noto 等官方字体。）
        problems.append(
            f"CharStrings 偏移 {chs} 小于 {MIN_CHARSTRINGS_OFFSET}，"
            f"而 CFF 表长 {cff_len/1048576:.1f} MB —— 偏移不可能有效"
        )

    # charset / FDArray / CharStrings 三者应分散；若挤在几百字节内即为损坏
    if None not in (cs, chs, fd):
        spread = max(cs, chs, fd) - min(cs, chs, fd)
        if spread < 512:
            problems.append(
                f"charset/FDArray/CharStrings 三者仅相隔 {spread} 字节，互相重叠"
            )

    if problems:
        print("  ==> BROKEN（CFF 结构损坏）")
        for p in problems:
            print(f"      - {p}")
        print()
        return True

    print("  ==> OK\n")
    return False


if __name__ == "__main__":
    args = sys.argv[1:] or [
        str(p) for suffix in ("*.otf", "*.ttc", "*.ttf")
        for p in Path.home().glob(f"Library/Fonts/{suffix}")
    ]
    args = [a for a in args if Path(a).exists()]
    results = [(a, audit(a)) for a in args]
    broken = [a for a, r in results if r is True]
    print(f"检测 {len(results)} 个字体，{len(broken)} 个损坏")
    for b in broken:
        print(f"  ! {b}")
    sys.exit(1 if broken else 0)
