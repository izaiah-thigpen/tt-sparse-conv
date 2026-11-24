"""Builds IEEE-format .docx papers from Prof. Parent's SoutheastCon template.

The template's package (styles, numbering, page setup, footer) is kept; only the
body and the figures change. Headings, figure captions, table titles and
references number themselves through the template's styles.

    python build.py abstract|full OUT.docx
"""
import os, re, shutil, struct, sys, zipfile
from xml.sax.saxutils import escape

TEMPLATE = '/home/claude/fmt/demo'
FIGS = '/home/claude/figs'
COL_EMU = 3200400          # 3.5 in minus a little: one column


def png_size(path):
    with open(path, 'rb') as f:
        f.read(16)
        w, h = struct.unpack('>II', f.read(8))
    return w, h


# ---------------------------------------------------------------- inline text
def runs(text, base=''):
    """*italic* and **bold** inline markup -> w:r elements."""
    out = []
    for part in re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', text):
        if not part:
            continue
        rpr = base
        if part.startswith('**'):
            part, rpr = part[2:-2], rpr + '<w:b/><w:bCs/>'
        elif part.startswith('*'):
            part, rpr = part[1:-1], rpr + '<w:i/><w:iCs/>'
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                   % ('<w:rPr>%s</w:rPr>' % rpr if rpr else '', escape(part)))
    return ''.join(out)


def p(style, text, ppr_extra=''):
    return '<w:p><w:pPr><w:pStyle w:val="%s"/>%s</w:pPr>%s</w:p>' % (style, ppr_extra, runs(text))


class Doc:
    def __init__(self):
        self.parts, self.images, self.pic = [], [], 100

    def add(self, xml):
        self.parts.append(xml)

    def title(self, t):
        self.add(p('Title', t))

    def author_break(self):
        # the template's author paragraph carries the one-column title section; names left out for blind review
        self.add(AUTHOR)

    def abstract(self, t):
        self.add('<w:p><w:pPr><w:pStyle w:val="Abstract"/></w:pPr><w:r><w:rPr><w:i/><w:iCs/></w:rPr>'
                 '<w:t>Abstract</w:t></w:r><w:r><w:t>—</w:t></w:r>%s</w:p>' % runs(t))

    def keywords(self, t):
        self.add('<w:p><w:pPr><w:pStyle w:val="Keywords"/></w:pPr><w:r><w:t>Keywords—</w:t></w:r>%s</w:p>' % runs(t))

    def h1(self, t):
        self.add(p('Heading1', t))

    def h2(self, t):
        self.add(p('Heading2', t))

    def h5(self, t):
        self.add(p('Heading5', t))

    def body(self, t):
        self.add(p('BodyText', t))

    def bullet_body(self, items):
        for it in items:
            self.add(p('BodyText', '• ' + it, '<w:ind w:start="9pt" w:hanging="9pt"/>'))

    def figure(self, png, caption, width_emu=COL_EMU):
        self.images.append(png)
        rid = 'rIdFig%d' % len(self.images)
        w, h = png_size(png)
        cx, cy = width_emu, int(width_emu * h / w)
        self.pic += 1
        self.add('<w:p><w:pPr><w:keepNext/><w:spacing w:before="6pt"/><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:noProof/></w:rPr><w:drawing>'
                 '<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="%d" cy="%d"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
                 '<wp:docPr id="%d" name="Figure %d"/><wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://purl.oclc.org/ooxml/drawingml/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                 '<a:graphic xmlns:a="http://purl.oclc.org/ooxml/drawingml/main"><a:graphicData uri="http://purl.oclc.org/ooxml/drawingml/picture">'
                 '<pic:pic xmlns:pic="http://purl.oclc.org/ooxml/drawingml/picture"><pic:nvPicPr><pic:cNvPr id="%d" name="fig%d.png"/><pic:cNvPicPr/></pic:nvPicPr>'
                 '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                 '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
                 '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
                 % (cx, cy, self.pic, self.pic, self.pic, self.pic, rid, cx, cy))
        self.add(p('figurecaption', caption))

    def table(self, title, header, rows, widths_pt):
        self.add(p('tablehead', title, '<w:keepNext/>'))
        tw = sum(widths_pt)
        grid = ''.join('<w:gridCol w:w="%d"/>' % round(w * 20) for w in widths_pt)

        def cell(text, w, style, jc='center'):
            return ('<w:tc><w:tcPr><w:tcW w:w="%gpt" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>'
                    '<w:p><w:pPr><w:pStyle w:val="%s"/><w:jc w:val="%s"/></w:pPr>%s</w:p></w:tc>') % (w, style, jc, runs(text))

        def row(cells, style, header=False):
            trpr = '<w:trPr><w:cantSplit/>%s<w:jc w:val="center"/></w:trPr>' % ('<w:tblHeader/>' if header else '')
            return '<w:tr>%s%s</w:tr>' % (trpr, ''.join(cell(c, w, style) for c, w in zip(cells, widths_pt)))

        b = '<w:%s w:val="single" w:sz="2" w:space="0" w:color="auto"/>'
        self.add('<w:tbl><w:tblPr><w:tblW w:w="%gpt" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>%s</w:tblBorders>'
                 '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:start w:w="2pt" w:type="dxa"/><w:end w:w="2pt" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>%s</w:tblGrid>%s%s</w:tbl>'
                 % (tw, ''.join(b % s for s in ('top', 'start', 'bottom', 'end', 'insideH', 'insideV')), grid,
                    row(header, 'tablecolhead', True), ''.join(row(r, 'tablecopy') for r in rows)))
        self.add('<w:p><w:pPr><w:spacing w:after="0pt"/></w:pPr></w:p>')

    def refs(self, items):
        for it in items:
            self.add(p('references', it))


# ---------------------------------------------------------------- template pieces
SRC = open(os.path.join(TEMPLATE, 'word', 'document.xml'), encoding='utf8').read()
HEAD = SRC[:SRC.index('<w:body>') + len('<w:body>')]
AUTHOR = re.search(r'<w:p [^>]*>(?:(?!</w:p>).)*?<w:pStyle w:val="Author"/>.*?</w:p>', SRC, re.S).group(0)
TAIL = re.search(r'<w:sectPr [^>]*>(?:(?!<w:sectPr).)*?</w:sectPr>\s*</w:body>\s*</w:document>\s*$', SRC, re.S).group(0)


def write(doc, out):
    work = out + '.d'
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(TEMPLATE, work)
    media = os.path.join(work, 'word', 'media')
    for f in os.listdir(media):
        os.remove(os.path.join(media, f))
    rels_path = os.path.join(work, 'word', '_rels', 'document.xml.rels')
    rels = open(rels_path, encoding='utf8').read()
    rels = re.sub(r'<Relationship Id="rId\d+" Type="[^"]+/image" Target="media/[^"]+"/>', '', rels)
    new = ''
    for i, png in enumerate(doc.images, 1):
        shutil.copy(png, os.path.join(media, 'fig%d.png' % i))
        new += '<Relationship Id="rIdFig%d" Type="http://purl.oclc.org/ooxml/officeDocument/relationships/image" Target="media/fig%d.png"/>' % (i, i)
    rels = rels.replace('</Relationships>', new + '</Relationships>')
    open(rels_path, 'w', encoding='utf8').write(rels)
    open(os.path.join(work, 'word', 'document.xml'), 'w', encoding='utf8').write(HEAD + ''.join(doc.parts) + TAIL)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(work):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, work))
    shutil.rmtree(work)


if __name__ == '__main__':
    import content
    which, out = sys.argv[1], sys.argv[2]
    d = Doc()
    getattr(content, which)(d)
    write(d, out)
    print('wrote', out)
