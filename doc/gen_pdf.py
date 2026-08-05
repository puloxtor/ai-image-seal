#!/usr/bin/env python3
"""Markdown -> styled PDF via ReportLab."""
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

W, H = A4
BRAND = colors.HexColor('#4FCEE4')
DARK = colors.HexColor('#1A1C1F')
MUTED = colors.HexColor('#898A8B')
LIGHT = colors.HexColor('#F0F0F0')


def _styles():
    getSampleStyleSheet()
    return {
        'title': ParagraphStyle('pdftitle', fontName='Helvetica-Bold', fontSize=26,
                                textColor=BRAND, spaceAfter=4*mm, leading=32),
        'sub': ParagraphStyle('sub', fontName='Helvetica', fontSize=10.5,
                              textColor=MUTED, spaceAfter=4*mm, leading=15),
        'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=17,
                             textColor=DARK, spaceBefore=8*mm, spaceAfter=3*mm, leading=22),
        'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=13,
                             textColor=DARK, spaceBefore=5*mm, spaceAfter=2*mm, leading=18),
        'h3': ParagraphStyle('h3', fontName='Helvetica-BoldOblique', fontSize=11,
                             textColor=DARK, spaceBefore=4*mm, spaceAfter=2*mm, leading=15),
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9.6,
                               textColor=DARK, leading=14.5, spaceAfter=2.6*mm,
                               alignment=TA_JUSTIFY),
        'bullet': ParagraphStyle('bullet', fontName='Helvetica', fontSize=9.6,
                                 textColor=DARK, leading=14.5, leftIndent=7*mm,
                                 spaceAfter=1.4*mm),
        'num': ParagraphStyle('num', fontName='Helvetica', fontSize=9.6,
                              textColor=DARK, leading=14.5, leftIndent=7*mm,
                              spaceAfter=1.4*mm),
        'code': ParagraphStyle('code', fontName='Courier', fontSize=8,
                               textColor=DARK, backColor=LIGHT, leftIndent=3*mm,
                               rightIndent=3*mm, spaceAfter=3*mm, leading=11),
        'th': ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=8.2,
                             textColor=DARK, leading=11.5),
        'td': ParagraphStyle('td', fontName='Helvetica', fontSize=8.2,
                             textColor=DARK, leading=11.5),
    }


def _inline(text):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'\\\*', '\x00', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`(.+?)`', r'<font name="Courier" size="8.4">\1</font>', text)
    return text.replace('\x00', '*')


def _parse_table(lines, styles):
    rows = []
    for line in lines:
        if re.match(r'^[\s|:\-]+$', line):
            continue
        rows.append([c.strip() for c in line.strip().strip('|').split('|')])
    if not rows:
        return None
    cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < cols:
            r.append('')
    avail = W - 50*mm
    first = min(0.42, max(0.20, 1.0/cols + 0.06)) if cols > 2 else 0.5
    widths = [avail*first] + [avail*(1-first)/(cols-1)]*(cols-1) if cols > 1 else [avail]
    body = [[Paragraph(_inline(c), styles['th'] if i == 0 else styles['td']) for c in row]
            for i, row in enumerate(rows)]
    t = Table(body, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.25, MUTED),
        ('TOPPADDING', (0, 0), (-1, -1), 1.6*mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.6*mm),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.8*mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.8*mm),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _build(md, title, subtitle, styles):
    story = [Paragraph(title, styles['title'])]
    if subtitle:
        story.append(Paragraph(subtitle, styles['sub']))
    story.append(HRFlowable(width='100%', thickness=1.5, color=BRAND, spaceAfter=6*mm))
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('```'):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            story.append(Preformatted('\n'.join(code), styles['code']))
            i += 1
            continue
        if '|' in line and i+1 < len(lines) and re.match(r'^[\s|:\-]+$', lines[i+1]):
            tl = []
            while i < len(lines) and '|' in lines[i]:
                tl.append(lines[i])
                i += 1
            t = _parse_table(tl, styles)
            if t:
                # keep a table whole: a split table loses its header row on the
                # continuation page, which reads as a broken table
                story += [KeepTogether([t]), Spacer(1, 3*mm)]
            continue
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            story.append(Paragraph(_inline(m.group(2)), styles[f'h{len(m.group(1))}']))
            i += 1
            continue
        if re.match(r'^(-{3,}|_{3,}|\*{3,})$', line.strip()):
            story.append(HRFlowable(width='100%', thickness=0.5, color=MUTED, spaceAfter=3*mm))
            i += 1
            continue
        m = re.match(r'^[\-\*\+]\s+(.*)', line)
        if m:
            story.append(Paragraph(f'\u2022 {_inline(m.group(1))}', styles['bullet']))
            i += 1
            continue
        m = re.match(r'^(\d+)\.\s+(.*)', line)
        if m:
            story.append(Paragraph(f'{m.group(1)}. {_inline(m.group(2))}', styles['num']))
            i += 1
            continue
        if not line.strip():
            story.append(Spacer(1, 1.6*mm))
            i += 1
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r'^(#{1,3}\s|[\-\*\+]\s|\d+\.\s|```|---$|___$)', lines[i]) and '|' not in lines[i]:
            para.append(lines[i])
            i += 1
        story.append(Paragraph(_inline(' '.join(para)), styles['body']))
    return story


def build_pdf(md_path, pdf_path, title, subtitle=''):
    styles = _styles()
    story = _build(Path(md_path).read_text(encoding='utf-8'), title, subtitle, styles)
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=25*mm, rightMargin=25*mm,
                            topMargin=20*mm, bottomMargin=18*mm, title=title,
                            author='Brave New Hair')

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(25*mm, 11*mm, 'Ghost Seal - AI disclosure standard - internal')
        canvas.drawRightString(W-25*mm, 11*mm, f'{d.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('PDF written:', pdf_path)


if __name__ == '__main__':
    build_pdf(sys.argv[1], sys.argv[2],
              sys.argv[3] if len(sys.argv) > 3 else 'Document',
              sys.argv[4] if len(sys.argv) > 4 else '')
