from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from game.models import Character, ChatMessage, GameState
from game.scenario import Scenario

_FONT_NAME = "STSong-Light"
_TABLE_CELL_CHAR_LIMIT = 200
_LONG_FIELD_KEYS = frozenset({"摘要", "记忆", "NPC", "任务", "背景", "模组", "背包", "技能"})
_ROLE_LABELS = {
    "user": "玩家",
    "assistant": "KP",
    "system": "系统",
}

# 配色
C_PRIMARY = colors.HexColor("#1e293b")
C_ACCENT = colors.HexColor("#b45309")
C_MUTED = colors.HexColor("#64748b")
C_LINE = colors.HexColor("#e2e8f0")
C_COVER_BG = colors.HexColor("#0f172a")
C_COVER_ACCENT = colors.HexColor("#fbbf24")
C_PLAYER_BG = colors.HexColor("#eff6ff")
C_PLAYER_BORDER = colors.HexColor("#3b82f6")
C_KP_BG = colors.HexColor("#f8fafc")
C_KP_BORDER = colors.HexColor("#94a3b8")
C_SYSTEM_BG = colors.HexColor("#fffbeb")
C_SYSTEM_BORDER = colors.HexColor("#f59e0b")
C_CARD_BG = colors.HexColor("#f1f5f9")


def _register_font() -> None:
    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))


def _safe(text: str) -> str:
    return escape(text or "").replace("\n", "<br/>")


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _format_code_markup(content: str) -> str:
    if _CJK_RE.search(content):
        return f'<font name="{_FONT_NAME}" color="#334155">{content}</font>'
    return f'<font face="Courier" color="#334155">{content}</font>'


def _inline_markdown(text: str) -> str:
    escaped = escape(text)
    code_spans: list[str] = []

    def _stash_code(match: re.Match[str]) -> str:
        code_spans.append(_format_code_markup(match.group(1)))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    escaped = _INLINE_CODE_RE.sub(_stash_code, escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", escaped)
    for idx, code_html in enumerate(code_spans):
        escaped = escaped.replace(f"\x00CODE{idx}\x00", code_html)
    return escaped


def _markdown_to_paragraph(text: str) -> str:
    if not text:
        return ""

    lines: list[str] = []
    in_code = False
    code_lines: list[str] = []

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                code_html = escape("\n".join(code_lines))
                lines.append(_format_code_markup(code_html.replace(chr(10), "<br/>")))
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            lines.append("")
            continue

        if stripped in {"---", "***", "___"}:
            lines.append("<br/>")
            continue

        header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header_match:
            level = len(header_match.group(1))
            size = max(11, 14 - level)
            lines.append(
                f'<b><font size="{size}">{_inline_markdown(header_match.group(2))}</font></b>'
            )
            continue

        if stripped.startswith("> "):
            lines.append(f"<i>{_inline_markdown(stripped[2:])}</i>")
            continue

        list_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        if list_match:
            lines.append(f"• {_inline_markdown(list_match.group(1))}")
            continue

        ordered_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ordered_match:
            lines.append(f"{ordered_match.group(1)}. {_inline_markdown(ordered_match.group(2))}")
            continue

        lines.append(_inline_markdown(line))

    if in_code and code_lines:
        code_html = escape("\n".join(code_lines))
        lines.append(_format_code_markup(code_html.replace(chr(10), "<br/>")))

    return "<br/>".join(lines)


def _rich_text(text: str, style: ParagraphStyle) -> str:
    markup = _markdown_to_paragraph(text)
    try:
        probe = Paragraph(markup, style)
        probe.wrap(500, 10000)
        return markup
    except Exception:
        return _safe(text)


_ROLE_HEADER_RE = re.compile(
    r"^(?:[◆◇•\-\*]\s*)?(?:【)?(?:玩家|KP|主持人|系统(?:\s*[/·]\s*检定)?)(?:】)?\s*$",
    re.IGNORECASE,
)


def _strip_embedded_role_header(content: str) -> str:
    lines = content.split("\n")
    while lines and _ROLE_HEADER_RE.match(lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def _slugify_filename(text: str, limit: int = 24) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned[:limit] or "game").strip("_")


def suggest_pdf_filename(
    scenario: Scenario,
    character: Character,
    *,
    exported_at: datetime | None = None,
) -> str:
    when = exported_at or datetime.now(timezone.utc)
    stamp = when.astimezone().strftime("%Y%m%d_%H%M")
    title = _slugify_filename(scenario.title)
    name = _slugify_filename(character.name, limit=12)
    return f"{title}_{name}_{stamp}.pdf"


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName=_FONT_NAME,
            fontSize=26,
            leading=32,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#cbd5e1"),
            alignment=TA_LEFT,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#94a3b8"),
            alignment=TA_LEFT,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontName=_FONT_NAME,
            fontSize=14,
            leading=18,
            textColor=C_PRIMARY,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=10,
            leading=16,
            textColor=C_PRIMARY,
            splitLongWords=True,
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=14,
            textColor=C_MUTED,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=9,
            leading=12,
            textColor=C_MUTED,
        ),
        "bubble_title": ParagraphStyle(
            "BubbleTitle",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=10,
            leading=15,
            textColor=C_PRIMARY,
            spaceAfter=0,
        ),
        "bubble_body": ParagraphStyle(
            "BubbleBody",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=10,
            leading=17,
            textColor=C_PRIMARY,
            splitLongWords=True,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName=_FONT_NAME,
            fontSize=8,
            leading=11,
            textColor=C_MUTED,
            alignment=TA_CENTER,
        ),
    }


def _section_header(title: str, styles: dict[str, ParagraphStyle], width: float) -> Table:
    bar = Table(
        [[Paragraph(f"<b>{_safe(title)}</b>", styles["section"])]],
        colWidths=[width],
    )
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_CARD_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 3, C_ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return bar


def _info_card(rows: list[list[str]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    table_rows = []
    for label, value in rows:
        table_rows.append(
            [
                Paragraph(_safe(label), styles["label"]),
                Paragraph(_safe(value), styles["body"]),
            ]
        )
    card = Table(table_rows, colWidths=[22 * mm, width - 22 * mm], splitByRow=1)
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, C_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, C_LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return card


def _should_use_long_block(label: str, value: str) -> bool:
    if label in _LONG_FIELD_KEYS:
        return True
    return len(value) > _TABLE_CELL_CHAR_LIMIT or value.count("\n") > 2


def _split_field_rows(rows: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    short: list[tuple[str, str]] = []
    long: list[tuple[str, str]] = []
    for label, value in rows:
        if _should_use_long_block(label, value):
            long.append((label, value))
        else:
            short.append((label, value))
    return short, long


def _long_field_block(
    label: str,
    value: str,
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list:
    body_style = ParagraphStyle(
        f"LongBody_{label}",
        parent=styles["body"],
        backColor=colors.white,
        borderPadding=8,
        spaceBefore=2,
        spaceAfter=6,
    )
    bar = Table(
        [[Paragraph(f"<b>{_safe(label)}</b>", styles["label"])]],
        colWidths=[width],
    )
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_CARD_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 2, C_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [
        bar,
        Paragraph(_rich_text(value, body_style), body_style),
        Spacer(1, 2 * mm),
    ]


def _append_field_section(
    story: list,
    rows: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
    width: float,
) -> None:
    short_rows, long_rows = _split_field_rows(rows)
    if short_rows:
        story.append(_info_card(list(short_rows), styles, width))
    if short_rows and long_rows:
        story.append(Spacer(1, 3 * mm))
    for label, value in long_rows:
        story.extend(_long_field_block(label, value, styles, width))


def _stat_grid(character: Character, styles: dict[str, ParagraphStyle], width: float) -> Table:
    from game.models import ABILITY_ORDER

    cells = []
    for key, field, label in ABILITY_ORDER:
        value = getattr(character, field)
        mod = character.modifier(key)
        cells.append(
            Paragraph(
                f"<b>{label}</b><br/>{value} <font color='#64748b'>({mod:+d})</font>",
                ParagraphStyle(
                    "StatCell",
                    parent=styles["body"],
                    fontSize=9,
                    leading=13,
                    alignment=TA_CENTER,
                ),
            )
        )
    row1 = cells[:3]
    row2 = cells[3:]
    grid = Table([row1, row2], colWidths=[width / 3.0] * 3)
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.6, C_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, C_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return grid


def _role_badge(role: str) -> tuple[str, colors.Color, colors.Color, colors.Color]:
    label = _ROLE_LABELS.get(role, role)
    if role == "user":
        return "【玩家】", C_PLAYER_BG, C_PLAYER_BORDER, C_PLAYER_BORDER
    if role == "system":
        return "【系统 · 检定】", C_SYSTEM_BG, C_SYSTEM_BORDER, C_SYSTEM_BORDER
    return "【KP】", C_KP_BG, C_KP_BORDER, C_KP_BORDER


def _chat_bubble(
    role: str,
    content: str,
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list:
    badge, bg, border, title_color = _role_badge(role)
    if role == "system":
        content = content.removeprefix("🎲 ").strip()
    content = _strip_embedded_role_header(content)

    title_style = ParagraphStyle(
        f"BubbleTitle_{role}",
        parent=styles["bubble_title"],
        textColor=title_color,
    )
    header = Table(
        [[Paragraph(escape(badge), title_style)]],
        colWidths=[width],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3, border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    body_style = ParagraphStyle(
        f"BubbleBody_{role}",
        parent=styles["bubble_body"],
        backColor=bg,
        borderPadding=(2, 10, 10, 12),
        leftIndent=0,
        spaceBefore=0,
        spaceAfter=0,
    )
    body = Paragraph(_rich_text(content, body_style), body_style)
    return [header, body, Spacer(1, 3 * mm)]


def _make_page_callbacks(scenario_title: str, character_name: str):
    def _draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(C_LINE)
        canvas.setLineWidth(0.5)
        y = 14 * mm
        canvas.line(doc.leftMargin, y + 4 * mm, A4[0] - doc.rightMargin, y + 4 * mm)
        canvas.setFont(_FONT_NAME, 8)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(doc.leftMargin, y, f"{scenario_title} · {character_name}")
        canvas.drawRightString(A4[0] - doc.rightMargin, y, f"第 {canvas.getPageNumber()} 页")
        canvas.restoreState()

    return _draw_footer, _draw_footer


def _cover_block(
    scenario: Scenario,
    character: Character,
    local_when: datetime,
    styles: dict[str, ParagraphStyle],
    width: float,
) -> Table:
    meta = (
        f"角色 {character.name}　·　{scenario.world or scenario.world_id}"
        f"　·　{local_when.strftime('%Y年%m月%d日 %H:%M')}"
    )
    block = Table(
        [
            [Paragraph(_safe(scenario.title), styles["cover_title"])],
            [Paragraph(_safe("AI 跑团 · 冒险记录"), styles["cover_sub"])],
            [Paragraph(_safe(meta), styles["cover_meta"])],
        ],
        colWidths=[width],
    )
    block.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_COVER_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 4, C_COVER_ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 16),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
                ("TOPPADDING", (0, 1), (-1, -1), 0),
            ]
        )
    )
    return block


def build_game_pdf(
    *,
    scenario: Scenario,
    character: Character,
    game_state: GameState,
    messages: list[ChatMessage],
    exported_at: datetime | None = None,
) -> bytes:
    _register_font()
    when = exported_at or datetime.now(timezone.utc)
    local_when = when.astimezone()
    styles = _build_styles()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=f"{scenario.title} - {character.name}",
        author="AI 跑团",
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin

    on_page = _make_page_callbacks(scenario.title, character.name)[0]
    story: list = []

    story.append(_cover_block(scenario, character, local_when, styles, content_width))
    story.append(Spacer(1, 8 * mm))
    story.append(
        HRFlowable(width="100%", thickness=0.6, color=C_LINE, spaceBefore=0, spaceAfter=8)
    )

    # 角色
    story.append(_section_header("角色卡", styles, content_width))
    story.append(Spacer(1, 3 * mm))
    _append_field_section(
        story,
        [
            ("背景", character.background),
            ("生命", f"HP {character.hp} / {character.effective_max_hp()}"),
            ("背包", character.format_inventory()),
            ("技能", character.format_skills()),
        ],
        styles,
        content_width,
    )
    story.append(Spacer(1, 4 * mm))
    story.append(_stat_grid(character, styles, content_width))
    story.append(Spacer(1, 8 * mm))

    # 进度
    story.append(_section_header("当前进度", styles, content_width))
    story.append(Spacer(1, 3 * mm))
    progress_rows = [
        ("场景", f"{game_state.current_scene}（{game_state.scene_id}）"),
        ("回合", str(game_state.turn_count)),
    ]
    if scenario.description:
        progress_rows.append(("模组", scenario.description))
    if scenario.tone:
        progress_rows.append(("基调", scenario.tone))
    active_quests = [q for q in game_state.active_quests if q.status == "active"]
    if active_quests:
        quest_text = "\n".join(
            f"• {q.title}：{q.description or '（无描述）'}" for q in active_quests
        )
        progress_rows.append(("任务", quest_text))
    if game_state.story_summary.strip():
        progress_rows.append(("摘要", game_state.story_summary.strip()))
    if game_state.memory_facts:
        facts = "\n".join(f"• {fact}" for fact in game_state.memory_facts[-10:])
        progress_rows.append(("记忆", facts))
    if game_state.npcs:
        npc_text = "\n".join(
            f"• {npc.name}（{npc.attitude}）"
            + (f" — {npc.notes}" if npc.notes else "")
            for npc in game_state.npcs
        )
        progress_rows.append(("NPC", npc_text))
    _append_field_section(story, progress_rows, styles, content_width)
    story.append(Spacer(1, 8 * mm))

    # 对话
    story.append(_section_header(f"游戏记录（共 {len(messages)} 条）", styles, content_width))
    story.append(Spacer(1, 4 * mm))
    if not messages:
        story.append(Paragraph(_safe("尚无对话记录。"), styles["muted"]))
    else:
        for msg in messages:
            content = msg.content.strip()
            if not content:
                continue
            story.extend(_chat_bubble(msg.role, content, styles, content_width))

    story.append(Spacer(1, 6 * mm))
    story.append(
        HRFlowable(width="40%", thickness=0.5, color=C_LINE, spaceBefore=4, spaceAfter=6)
    )
    story.append(Paragraph(_safe("由 AI 跑团导出 · 仅供阅读与分享"), styles["footer"]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
