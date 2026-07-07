from __future__ import annotations

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak

BASE = Path(r'C:\Users\mathi\projects\forgegraph\backend\.hermes\career_ops_kiddom_20260702')
NAVY = colors.HexColor('#112B46')
GOLD = colors.HexColor('#C9A227')
BLUE = colors.HexColor('#163B63')
TEXT = colors.HexColor('#222222')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Name', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.white, fontSize=20, leading=24, spaceAfter=4))
styles.add(ParagraphStyle(name='Contact', parent=styles['Normal'], alignment=TA_CENTER, textColor=colors.white, fontSize=8.8, leading=11))
styles.add(ParagraphStyle(name='Section', parent=styles['Heading2'], textColor=BLUE, fontName='Times-Bold', fontSize=12.5, leading=15, spaceBefore=10, spaceAfter=3))
styles.add(ParagraphStyle(name='Body', parent=styles['Normal'], textColor=TEXT, fontSize=9.2, leading=11.8, spaceAfter=4))
styles.add(ParagraphStyle(name='Role', parent=styles['Normal'], textColor=TEXT, fontName='Helvetica-Bold', fontSize=9.7, leading=12, spaceBefore=5, spaceAfter=1))
styles.add(ParagraphStyle(name='Meta', parent=styles['Normal'], textColor=colors.HexColor('#555555'), fontSize=8.8, leading=10.5, spaceAfter=2))
styles.add(ParagraphStyle(name='CvBullet', parent=styles['Normal'], leftIndent=12, firstLineIndent=-7, fontSize=8.8, leading=11, spaceAfter=2.3))


def clean(s: str) -> str:
    return (s.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;'))


def header(story):
    from reportlab.platypus import Table, TableStyle
    data = [[Paragraph('Miguel Athie', styles['Name'])], [Paragraph('Mexico City, MX | miguel.athien@gmail.com | +52 55 3900 3599 | GitHub: https://github.com/MikeAthie', styles['Contact'])]]
    t = Table(data, colWidths=[7.1*inch])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),NAVY),('BOX',(0,0),(-1,-1),0,NAVY),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(t)
    story.append(HRFlowable(width='100%', thickness=1.5, color=GOLD, spaceBefore=0, spaceAfter=8))


def parse_cv(md: str):
    story=[]
    header(story)
    lines=md.splitlines()
    skip_title=True
    in_bullets=False
    for line in lines:
        line=line.strip()
        if not line:
            continue
        if line.startswith('# Miguel') or line.startswith('Mexico City'):
            continue
        if line.startswith('## '):
            story.append(Paragraph(clean(line[3:]).upper(), styles['Section']))
            story.append(HRFlowable(width='100%', thickness=.6, color=GOLD, spaceBefore=0, spaceAfter=4))
        elif line.startswith('### '):
            story.append(Paragraph(clean(line[4:]), styles['Role']))
        elif line.startswith('- '):
            story.append(Paragraph('• ' + clean(line[2:]), styles['CvBullet']))
        elif '|' in line and not line.startswith('GitHub'):
            story.append(Paragraph(clean(line), styles['Meta']))
        else:
            story.append(Paragraph(clean(line), styles['Body']))
    return story


def parse_letter(text: str):
    story=[]
    header(story)
    for block in text.split('\n\n'):
        block=block.strip()
        if not block or block.startswith('Miguel Athie') or block.startswith('Mexico City') or block.startswith('miguel.') or block.startswith('GitHub:'):
            continue
        if block == 'TurnKey Tech Staffing / Kiddom Hiring Team':
            story.append(Paragraph(clean(block), styles['Role']))
        else:
            story.append(Paragraph(clean(block).replace('\n','<br/>'), styles['Body']))
            story.append(Spacer(1, 4))
    return story


def render(infile: str, outfile: str, kind: str):
    doc=SimpleDocTemplate(str(BASE/outfile), pagesize=LETTER, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.45*inch, bottomMargin=.45*inch)
    txt=(BASE/infile).read_text(encoding='utf-8')
    story=parse_cv(txt) if kind=='cv' else parse_letter(txt)
    doc.build(story)

render('Miguel-Athie-Kiddom-Senior-Backend-Engineer-CV.md','Miguel-Athie-Kiddom-Senior-Backend-Engineer-CV.pdf','cv')
render('Miguel-Athie-Kiddom-Senior-Backend-Engineer-Cover-Letter.md','Miguel-Athie-Kiddom-Senior-Backend-Engineer-Cover-Letter.pdf','letter')
print(BASE)
