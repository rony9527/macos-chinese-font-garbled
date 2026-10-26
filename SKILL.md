---
name: macos-chinese-font-garbled
description: >
  Diagnose and fix Chinese text rendering as wrong-but-real characters (乱码) instead of
  tofu boxes or Latin mojibake, across multiple macOS apps at once (Flutter apps like
  FlClash/ClashX, Chrome/Safari, Terminal). Use when Chinese renders as plausible-looking
  but wrong hanzi (零窥菱伿), when only SOME strings are affected while others in the same
  UI are correct, or when fixing one app's font settings did nothing. The signature clue is
  that the damage is system-wide yet inconsistent — some codepoints resolve, others don't.
---

# macOS 中文乱码（字形映射错误）诊断与修复
## 1. 先分型：三种乱码，病因完全不同

**这一步不能跳过。** 分错类型，后面全错。

| 现象 | 病因 | 修法 |
|---|---|---|
| 显示 `路`、`ç±` 等拉丁/UTF-8 串 | 文本**编码**解析错（locale、解码器） | 改 `LANG`/`LC_ALL`，与本技能无关 |
| 显示方块 `□□□` / tofu | **缺字形**——没有任何字体含该码点 | 装覆盖该码点的字体 |
| 显示成**另一个真实汉字**（「路」→「零窥菱伿」） | **字体 CFF 索引偏移损坏**，引擎按错位数据取到相邻字形 outline | 本技能 |

第三类的判断要点：

- 同一界面里，一部分中文正确、一部分错误（「路由工具」正常，「零窥菱伿」错）
- 错误字符串**反复稳定出现同一批**（同一次出现三次「譿灿痰絞」）
- **多个互不相关的应用同时中招**（FlClash + Chrome/YouTube + Terminal）

第三点最关键：浏览器和 Flutter 应用都坏，就**不要**去改单个应用的设置——那是系统级字体问题。

## 2. 取证：证明字体文件结构损坏

不要凭"这字体是第三方来的"下结论。**解析二进制**。

随技能的 `audit_fonts.py` 已封装全部检测，直接跑：

```bash
python3 ~/.claude/skills/macos-chinese-font-garbled/audit_fonts.py \
    ~/Library/Fonts/PingFangSC-Regular.otf          # 可疑字体
```

不带参数则扫 `~/Library/Fonts/` 全部字体。退出码 0 = 正常，1 = 有损坏。

### 2.1 判据：CFF 索引偏移不可能有效

对 CFF/OTF 字体，从 TopDICT 取出三个偏移量。**只有两条判据可靠**：

| 判据 | 阈值 |
|---|---|
| `CharStrings` 偏移 < 1024 | 而 CFF 表长数十 MB |
| `charset`/`FDArray`/`CharStrings` 三者间距 < 512 字节 | 三者互相重叠 |

实测对照（本次案例）：

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

**为什么这会导致"错字"而非"方块"**：引擎按 CFF 规范解析轮廓数据时，头部索引偏移指向错位区域，取到的是相邻字形的 outline——于是渲染出**另一个真实汉字**。这是第三类乱码独有的机制，也是它比方块更难排查的原因。

### 2.2 官方字体的正常形态（基线）

| 特征 | 官方正常 | 损坏副本 |
|---|---|---|
| 容器 | `.ttc` 集合（`ttcf`，多字体内涵） | 单个 `.otf` |
| CFF String Index | ~23 项 | 5 项 |
| TopDICT 偏移 | charset≈13-16k，CharStrings≈14-16k，FDArray≈14M | 三者挤在 <100 字节 |
| 系统原生 PingFang | `/System/Library/PrivateFrameworks/FontServices.framework/Versions/A/Resources/Reserved/PingFangUI.ttc`（ttcf，32 字体，glyf 轮廓） | — |

> **这两条不能当判据**（本次踩过，会误伤官方字体，已从脚本移除）：
> - `SID == gid` —— 官方 CID 字体（Noto 等）同样如此，是正常形态
> - `FDArray 偏移 > CharStrings 偏移` —— Noto 的 FDArray=14191576 > CharStrings=14229，工作完全正常
>
> `String Index 条目少` 可作辅助线索，但不可单独定罪。

### 2.3 先备好官方字体，再动坏字体

顺序不能反：先装好可用的，再移走坏的。否则会从"部分错字"恶化为"全方块"。

```bash
mkdir -p ~/Downloads/fonts-fix && cd ~/Downloads/fonts-fix
curl -sL -o NotoSansCJK-OTC.zip \
  "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/03_NotoSansCJK-OTC.zip"
unzip -o -q NotoSansCJK-OTC.zip
cp NotoSansCJK-Regular.ttc NotoSansCJK-Medium.ttc NotoSansCJK-Bold.ttc ~/Library/Fonts/
```

## 3. 修复

**只移走，不删除**——保留可回滚。

```bash
mkdir -p ~/Library/Fonts/broken-backup
mv ~/Library/Fonts/<可疑字体> ~/Library/Fonts/broken-backup/
```

然后刷新（比重启轻）：

```bash
killall -HUP WindowServer
killall -HUP fontd
pkill -9 <受影响App> && open -a <受影响App>
```

浏览器要硬重载：`Cmd+Shift+R`。

## 4. 验证

截图比对，不要凭感觉。确认之前乱掉的那几处字符串现在正确：

```bash
screencapture -x -o /tmp/after.png
```

逐项核对：原先乱码的菜单项、原先正确的中文（确认没被改坏）、浏览器网页中文、Terminal 中文。

## 5. 回滚

```bash
mv ~/Library/Fonts/broken-backup/<字体> ~/Library/Fonts/
killall -HUP WindowServer
```

## 常见误判（本次踩过）

- **不要先重启应用/改应用语言设置**。YouTube 也坏，就说明与单个应用无关；改应用设置是无效功。
- **不要只移走坏字体就以为完事**。若系统无可用中文字体兜底，会从"部分错字"恶化为"全方块"——比之前更糟。**先装官方 Noto，再移走坏字体**，顺序不能反。
- **不要 `rm -rf` 删字体缓存目录当万能药**。先 `du -sh` 看它是不是空的（本次就是 0B，白折腾）。
- **配置文件正常不代表渲染正常**。订阅 YAML 是合法 UTF-8、节点名中文完好，问题纯粹在字体层。查数据编码会完全找错方向。

## 判据速查

```
中文变拉丁串        → 编码问题，改 locale
中文变方块          → 缺字形，装字体
中文变成另一个汉字  → CFF 索引偏移损坏，本技能
多个应用同时中招    → 系统级字体，别改应用设置
部分对部分错        → 引擎按错位 outline 渲染，查 CFF TopDICT 偏移
```
