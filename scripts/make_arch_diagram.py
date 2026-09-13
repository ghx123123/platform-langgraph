"""Generate the 功能架构图 (functional architecture diagram) for the 平台说明书.

Pure-PIL rendering: 图内不出现任何本机字体名以外的依赖，中文用系统自带黑体/宋体。
Output: docs/申报书/img/A1-功能架构图.png

Usage: python scripts/make_arch_diagram.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("D:/paper/dsh/platform-langgraph")
OUT = ROOT / "docs" / "申报书" / "img" / "A1-功能架构图.png"

W, H = 2400, 1290
SCALE = 2  # 超采样后缩小，边缘更干净

HEI = "C:/Windows/Fonts/simhei.ttf"
SONG = "C:/Windows/Fonts/simsun.ttc"
FONT_CANDIDATES = [HEI, "C:/Windows/Fonts/msyh.ttc", SONG]

# 配色（与平台界面同色系：深蓝主色 + 灰蓝辅助）
INK = (26, 46, 74)
ACCENT = (37, 99, 235)
LAYER_BG = [(238, 244, 251), (237, 244, 252), (233, 243, 250), (232, 241, 250), (245, 247, 250)]
LAYER_EDGE = [(180, 200, 224), (176, 198, 224), (170, 196, 220), (168, 194, 220), (198, 208, 220)]
BOX_BG = (255, 255, 255)
BOX_EDGE = (150, 175, 205)
AGENT_BG = (232, 241, 255)
AGENT_EDGE = (37, 99, 235)
FLOW = (110, 145, 185)


def font(size, bold=False):
    for path in ([HEI, "C:/Windows/Fonts/msyhbd.ttc"] if bold else FONT_CANDIDATES):
        try:
            return ImageFont.truetype(path, size * SCALE)
        except OSError:
            continue
    return ImageFont.load_default()


def text_center(d, xy, s, f, fill):
    x, y = xy
    l, t, r, b = d.textbbox((0, 0), s, font=f)
    d.text((x - (r - l) / 2 - l, y - (b - t) / 2 - t), s, font=f, fill=fill)


def wrap(d, s, f, max_w):
    lines, cur = [], ""
    for ch in s:
        if d.textlength(cur + ch, font=f) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def box(d, x, y, w, h, title, body="", *, bg=BOX_BG, edge=BOX_EDGE,
        title_size=30, body_size=22, radius=None, title_color=INK):
    r = radius if radius is not None else 12 * SCALE
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=bg, outline=edge,
                        width=max(1, SCALE))
    ft, fb = font(title_size, True), font(body_size)
    if body:
        text_center(d, (x + w / 2, y + 26 * SCALE), title, ft, title_color)
        yy = y + 52 * SCALE
        # body supports explicit newlines; each paragraph also wraps to the box width
        for para in body.split(chr(10)):
            for line in wrap(d, para, fb, w - 22 * SCALE)[:4]:
                text_center(d, (x + w / 2, yy), line, fb, (72, 92, 116))
                yy += 27 * SCALE
    else:
        text_center(d, (x + w / 2, y + h / 2), title, ft, title_color)


def arrow_down(d, x, y1, y2, color=FLOW):
    d.line([x, y1, x, y2], fill=color, width=2 * SCALE)
    a = 8 * SCALE
    d.polygon([(x, y2 + a), (x - a * 0.7, y2), (x + a * 0.7, y2)], fill=color)


def arrow_right(d, x1, x2, y, color=FLOW, dashed=False):
    if dashed:
        seg, gap, x = 9 * SCALE, 6 * SCALE, x1
        while x < x2 - 8 * SCALE:
            d.line([x, y, min(x + seg, x2), y], fill=color, width=2 * SCALE)
            x += seg + gap
    else:
        d.line([x1, y, x2, y], fill=color, width=2 * SCALE)
    a = 8 * SCALE
    d.polygon([(x2 + a, y), (x2, y - a * 0.7), (x2, y + a * 0.7)], fill=color)


def build():
    img = Image.new("RGB", (W * SCALE, H * SCALE), "white")
    d = ImageDraw.Draw(img)
    M = 34 * SCALE
    LW = W * SCALE - M * 2

    f_title = font(42, True)
    f_layer = font(30, True)
    f_note = font(21)

    text_center(d, (W * SCALE / 2, M + 22 * SCALE), "多智能体课程教学设计平台  功能架构", f_title, INK)

    y = M + 74 * SCALE

    # ---------------- 交互层 ----------------
    lh = 132 * SCALE
    d.rounded_rectangle([M, y, M + LW, y + lh], radius=14 * SCALE,
                        fill=LAYER_BG[0], outline=LAYER_EDGE[0], width=SCALE)
    text_center(d, (M + 34 * SCALE, y + lh / 2), "交互层", f_layer, ACCENT)
    mods = [
        ("① 中台总览", "跨课程数据总览\n教学资料流转总览"),
        ("② 课程资料库", "本地资料结构化归集\n渐进式索引与按需解析"),
        ("③ 资料单元", "教材研读与结构化\n知识大纲多版本管理"),
        ("④ 课程设计", "多智能体教学设计\n课堂演练与复盘"),
        ("⑤ 成果中心", "内容编排与教案定稿\nWord 模板化导出"),
    ]
    bx = M + 120 * SCALE
    bw = (LW - 150 * SCALE) / 5 - 12 * SCALE
    for i, (t, b) in enumerate(mods):
        x = bx + i * (bw + 12 * SCALE)
        box(d, x, y + 14 * SCALE, bw, lh - 28 * SCALE, t, b,
            title_size=27, body_size=19)
    # 模块间流转
    for i in range(4):
        x1 = bx + i * (bw + 12 * SCALE) + bw + 2 * SCALE
        arrow_right(d, x1, x1 + 8 * SCALE, y + lh / 2)
    y += lh + 16 * SCALE
    arrow_down(d, W * SCALE / 2, y - 15 * SCALE, y + 8 * SCALE)

    # ---------------- 编排层 ----------------
    y += 12 * SCALE
    lh2 = 250 * SCALE
    d.rounded_rectangle([M, y, M + LW, y + lh2], radius=14 * SCALE,
                        fill=LAYER_BG[1], outline=LAYER_EDGE[1], width=SCALE)
    text_center(d, (M + 34 * SCALE, y + lh2 / 2), "编排层", f_layer, ACCENT)
    text_center(d, (M + LW / 2, y + 22 * SCALE), "七节点教学设计流水线（LangGraph 工作流编排）", font(25, True), INK)
    nodes = ["1 资料分析", "2 PPT V1", "3 用户审阅", "4 课堂演练", "5 督导复盘", "6 版本修订", "7 定稿"]
    nx = M + 120 * SCALE
    nw = (LW - 140 * SCALE) / 7 - 10 * SCALE
    ny = y + 48 * SCALE
    for i, n in enumerate(nodes):
        x = nx + i * (nw + 10 * SCALE)
        fill = (219, 234, 254) if i in (2, 3, 4) else BOX_BG
        edge = ACCENT if i in (2, 3, 4) else BOX_EDGE
        box(d, x, ny, nw, 46 * SCALE, n, "", bg=fill, edge=edge, title_size=21)
        if i < 6:
            arrow_right(d, x + nw + 1 * SCALE, x + nw + 8 * SCALE, ny + 23 * SCALE)
    text_center(d, (M + LW / 2, ny + 66 * SCALE),
                "教师决策点：③ 审阅门    ④ 介入 / 暂停    ⑤ 修改计划确认",
                f_note, (55, 90, 140))
    # 演练编排子模块
    sub = [
        ("课堂回合推进器", "按教学事件推进回合\n页面边界自动结算指令"),
        ("教师指令生命周期", "意图 × 范围 建模\n约束继承 / 落实 / 撤销"),
        ("督导评价与修订", "九维度评分 + 逐页修改计划\n生成 RevisionPatch"),
    ]
    sx = M + 120 * SCALE
    sw = (LW - 140 * SCALE) / 3 - 10 * SCALE
    sy = ny + 88 * SCALE
    for i, (t, b) in enumerate(sub):
        x = sx + i * (sw + 10 * SCALE)
        box(d, x, sy, sw, 96 * SCALE, t, b, bg=(250, 252, 255),
            title_size=23, body_size=19)
    y += lh2 + 16 * SCALE
    arrow_down(d, W * SCALE / 2, y - 15 * SCALE, y + 8 * SCALE)

    # ---------------- 智能体层 ----------------
    y += 12 * SCALE
    lh3 = 236 * SCALE
    d.rounded_rectangle([M, y, M + LW, y + lh3], radius=14 * SCALE,
                        fill=LAYER_BG[2], outline=LAYER_EDGE[2], width=SCALE)
    text_center(d, (M + 34 * SCALE, y + lh3 / 2), "智能体层", f_layer, ACCENT)
    agents = [
        ("教师智能体", "1 个\n讲授 · 答疑 · 反馈\n执行教师指令", True),
        ("拓展型学生 A", "1 个\n追问原理与边界\n提出迁移性问题", False),
        ("进阶型学生 B", "1 个\n概念理解与应用追问\n代表多数学生困惑", False),
        ("基础型学生 C", "1 个\n基础概念提问\n暴露知识盲点", False),
        ("督导智能体", "1 个\n旁听记录 · 逐页评价\n出具评分报告与建议", True),
    ]
    ax = M + 120 * SCALE
    aw = (LW - 140 * SCALE) / 5 - 10 * SCALE
    ay = y + 44 * SCALE
    for i, (t, b, hi) in enumerate(agents):
        x = ax + i * (aw + 10 * SCALE)
        box(d, x, ay, aw, 132 * SCALE, t, b,
            bg=AGENT_BG if hi else BOX_BG,
            edge=AGENT_EDGE if hi else BOX_EDGE,
            title_size=24, body_size=19,
            title_color=ACCENT if hi else INK)
    # 课堂内的交互回路
    loop_y = ay + 132 * SCALE + 26 * SCALE
    lx1 = ax + aw * 0.5
    lx2 = ax + (aw + 10 * SCALE) * 3 + aw * 0.5
    d.line([lx1, loop_y, lx1, loop_y + 14 * SCALE], fill=FLOW, width=2 * SCALE)
    d.line([lx2, loop_y, lx2, loop_y + 14 * SCALE], fill=FLOW, width=2 * SCALE)
    arrow_right(d, lx1, lx2, loop_y + 14 * SCALE, dashed=False)
    text_center(d, ((lx1 + lx2) / 2, loop_y + 34 * SCALE),
                "课堂事件流：讲授 → 提问 → 回答 → 反馈（全部落库为带序号事件，供督导取证）",
                f_note, (55, 90, 140))
    y += lh3 + 16 * SCALE
    arrow_down(d, W * SCALE / 2, y - 15 * SCALE, y + 8 * SCALE)

    # ---------------- 服务层 ----------------
    y += 12 * SCALE
    lh4 = 152 * SCALE
    d.rounded_rectangle([M, y, M + LW, y + lh4], radius=14 * SCALE,
                        fill=LAYER_BG[3], outline=LAYER_EDGE[3], width=SCALE)
    text_center(d, (M + 34 * SCALE, y + lh4 / 2), "服务层", f_layer, ACCENT)
    svcs = [
        ("资料解析服务", "PDF / DOCX / PPTX / XLS\n正文提取与结构化"),
        ("工作流服务", "运行状态与事件流\nWebSocket 实时推送"),
        ("文档与导出服务", "DOCX 模板识别与填充\n原页预览与下载"),
        ("数据持久化", "课程资料 / 设计 / 课堂事件\n版本快照与引用溯源"),
    ]
    vx = M + 120 * SCALE
    vw = (LW - 140 * SCALE) / 4 - 10 * SCALE
    for i, (t, b) in enumerate(svcs):
        x = vx + i * (vw + 10 * SCALE)
        box(d, x, y + 26 * SCALE, vw, 100 * SCALE, t, b, title_size=24, body_size=19)
    y += lh4 + 16 * SCALE
    arrow_down(d, W * SCALE / 2, y - 15 * SCALE, y + 8 * SCALE)

    # ---------------- 模型层 ----------------
    y += 12 * SCALE
    lh5 = 96 * SCALE
    d.rounded_rectangle([M, y, M + LW, y + lh5], radius=14 * SCALE,
                        fill=LAYER_BG[4], outline=LAYER_EDGE[4], width=SCALE)
    text_center(d, (M + 34 * SCALE, y + lh5 / 2), "模型层", f_layer, ACCENT)
    box(d, M + 120 * SCALE, y + 16 * SCALE, LW - 160 * SCALE, lh5 - 32 * SCALE,
        "多厂商大语言模型统一调用（本地桥接进程 / 流式输出 / 失败重试 / 错误中文化）",
        "", title_size=23)

    y += lh5 + 10 * SCALE

    # 右侧竖排说明
    img = img.resize((W, H), Image.LANCZOS)
    img.save(OUT)
    print("已生成:", OUT, img.size)


if __name__ == "__main__":
    build()
