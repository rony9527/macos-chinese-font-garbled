# macOS 中文乱码（字形映射错误）诊断与修复

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org)

> **中文说明**
>
> macOS 上中文突然变成「另一个看得懂但错了的字」——比如「路由」显示成「零窥菱伿」——而且不是某一个软件的问题，FlClash、Chrome、YouTube、终端全都中招。
>
> 这不是编码错误，也不是缺字体，而是字体文件的 **CFF 索引偏移损坏**：渲染引擎按规范去读字形轮廓时，头部偏移指向了错位区域，取到的是相邻字形的轮廓，于是渲染出另一个真实汉字。
>
> 本仓库提供一个零依赖的检测脚本，直接判定哪个字体坏了；再配上「先装官方字体、后移走坏字体」的修复顺序，避免问题从「部分错字」恶化成「满屏方块」。
>
> 这条排查路径来自一次真实的故障：FlClash 界面中文乱码，同时 YouTube 网页中文也坏。因为跨应用同时中招，所以断定与单个应用无关，最终解析字体二进制定位到 `~/Library/Fonts/` 里一份损坏的 PingFang SC 副本。

---

macOS 上中文显示成**另一个真实汉字**（「路」→「零窥菱伿」）时，用本技能定位并修复。

这不是编码问题，也不是缺字体——是字体文件的 CFF 索引偏移损坏，导致渲染引擎按错位数据取到了相邻字形的轮廓。

## 作者

**lpeng**（GitHub: [@rony9527](https://github.com/rony9527)）

本项目由作者在与 AI 助手协作排障的过程中整理而成——排查思路、判据阈值与实测数据由作者验证确定，代码与文档由 AI 协助撰写。

## 快速使用

```bash
python3 audit_fonts.py                    # 扫描 ~/Library/Fonts/ 全部字体
python3 audit_fonts.py <font-file>        # 检测指定字体
```

退出码 `0` = 全部正常，`1` = 发现损坏。可直接用于脚本。

## 先分型：三种乱码，病因完全不同

| 现象 | 病因 | 修法 |
|---|---|---|
| `路`、`ç±` 等拉丁/UTF-8 串 | 文本**编码**解析错（locale、解码器） | 改 `LANG` / `LC_ALL` |
| 方块 `□□□` / tofu | **缺字形**——没有任何字体含该码点 | 装覆盖该码点的字体 |
| **另一个真实汉字** | **CFF 索引偏移损坏** | 本技能 |

第三类的识别线索：

- 同一界面里，一部分中文正确、一部分错误（「路由工具」正常，「零窥菱伿」错）
- 错误字符串**反复稳定出现同一批**
- **多个互不相关的应用同时中招**（FlClash + Chrome/YouTube + Terminal）

最后一点最关键：浏览器和 Flutter 应用都坏，说明是**系统级字体问题**，不要改单个应用的设置。

## 判据

对 CFF/OTF 字体，从 TopDICT 取出三个偏移量。**只有两条判据可靠**：

| 判据 | 阈值 |
|---|---|
| `CharStrings` 偏移 < 1024 | 而 CFF 表长数十 MB |
| `charset` / `FDArray` / `CharStrings` 三者间距 < 512 字节 | 三者互相重叠 |

实测对照：

```
坏字体 PingFangSC-Regular.otf
  CFF 表长 11.6 MB
  TopDICT 偏移: charset=276, CharStrings=354, FDArray=289
  ==> BROKEN
      - CharStrings 偏移 354 小于 1024，而 CFF 表长 11.6 MB
      - 三者仅相隔 78 字节，互相重叠

官方 NotoSansCJK-Regular.ttc
  CFF 表长 14.7 MB
  TopDICT 偏移: charset=13865, CharStrings=14229, FDArray=14191576
  ==> OK
```

**为什么表现为"错字"而非"方块"**：引擎按 CFF 规范解析轮廓数据时，头部索引偏移指向错位区域，取到的是相邻字形的 outline——于是渲染出另一个真实汉字。这是它比方块更难排查的原因。

### 不能当判据的两条

以下特征在**官方正常字体**中同样存在，用作判据会误报（本项目踩过，已从检测逻辑移除）：

- `SID == gid` —— 官方 CID 字体（Noto 等）同样如此，是正常形态
- `FDArray 偏移 > CharStrings 偏移` —— Noto 的 FDArray=14191576 > CharStrings=14229，工作完全正常

`String Index 条目少` 可作辅助线索，但不可单独定罪。

## 修复流程

**顺序不能反**：先装好可用的官方字体，再移走坏字体。否则会从"部分错字"恶化为"全方块"，比之前更糟。

### 1. 安装官方 Noto Sans CJK

```bash
mkdir -p ~/Downloads/fonts-fix && cd ~/Downloads/fonts-fix
curl -sL -o NotoSansCJK-OTC.zip \
  "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/03_NotoSansCJK-OTC.zip"
unzip -o -q NotoSansCJK-OTC.zip
cp NotoSansCJK-Regular.ttc NotoSansCJK-Medium.ttc NotoSansCJK-Bold.ttc ~/Library/Fonts/
```

### 2. 移走坏字体（不删除，保留回滚）

```bash
mkdir -p ~/Library/Fonts/broken-backup
mv ~/Library/Fonts/<可疑字体> ~/Library/Fonts/broken-backup/
```

### 3. 刷新

```bash
killall -HUP WindowServer
killall -HUP fontd
pkill -9 <受影响App> && open -a <受影响App>
```

浏览器要硬重载：`Cmd+Shift+R`。

### 4. 验证

截图比对，不要凭感觉。确认原先乱掉的字符串现在正确、原先正确的中文没被改坏。

### 5. 回滚

```bash
mv ~/Library/Fonts/broken-backup/<字体> ~/Library/Fonts/
killall -HUP WindowServer
```

## 常见误判

- **不要先重启应用 / 改应用语言设置**。YouTube 也坏，就说明与单个应用无关。
- **不要只移走坏字体就以为完事**。系统必须有可用中文字体兜底。
- **不要 `rm -rf` 删字体缓存目录当万能药**。先 `du -sh` 看它是不是空的。
- **配置文件正常不代表渲染正常**。订阅 YAML 是合法 UTF-8、节点名中文完好，问题纯粹在字体层。查数据编码会完全找错方向。

## 判据速查

```
中文变拉丁串        → 编码问题，改 locale
中文变方块          → 缺字形，装字体
中文变成另一个汉字  → CFF 索引偏移损坏，用 audit_fonts.py
多个应用同时中招    → 系统级字体，别改应用设置
部分对部分错        → 引擎按错位 outline 渲染，查 CFF TopDICT 偏移
```

## 作为 Claude Code 技能使用

本仓库同时是一个 Claude Code skill。放入技能目录即可被自动发现：

```bash
git clone <repo-url> ~/.claude/skills/macos-chinese-font-garbled
```

触发条件：中文显示成另一个真实汉字、只有部分字符串受影响、改单个应用设置无效。

## 依赖

纯 Python 3 标准库（`struct` / `sys` / `pathlib`），无第三方依赖。

## 作者

**lpeng**（GitHub: [@rony9527](https://github.com/rony9527)）

问题定位、判据阈值与实测数据由作者验证确定；代码与文档由 AI 协助撰写。

## License

MIT — 详见 [LICENSE](LICENSE)
