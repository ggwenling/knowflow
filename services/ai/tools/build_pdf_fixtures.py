"""Original synthetic CC0 PDF boundary fixtures. Run in locked dev environment."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image, ImageDraw
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader,PdfWriter

root=Path(__file__).resolve().parents[1]/'tests/fixtures/pdf'
root.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

def text_pdf():
    stream=BytesIO();c=Canvas(stream,invariant=1,pageCompression=0)
    c.setFont('STSong-Light',12);c.drawString(72,720,'合成第一页：上传后等待索引完成。');c.showPage()
    c.showPage()  # empty middle page must not shift page 3 to page 2
    c.setFont('STSong-Light',12);c.drawString(72,720,'合成第三页：删除后不可再次检索。');c.showPage();c.save()
    return stream.getvalue()

normal=text_pdf();(root/'chinese-pages.pdf').write_bytes(normal)
blank=BytesIO();c=Canvas(blank,invariant=1);c.showPage();c.save();(root/'blank.pdf').write_bytes(blank.getvalue())
image=Image.new('RGB',(300,80),'white');ImageDraw.Draw(image).text((8,20),'Synthetic scanned content',fill='black')
scanned=BytesIO();c=Canvas(scanned,invariant=1);c.drawImage(ImageReader(image),72,600,width=300,height=80);c.showPage();c.save()
(root/'image-only.pdf').write_bytes(scanned.getvalue())
writer=PdfWriter();writer.append(PdfReader(BytesIO(normal)));writer.encrypt('synthetic-test-password')
encrypted=BytesIO();writer.write(encrypted);(root/'encrypted.pdf').write_bytes(encrypted.getvalue())
(root/'malformed.pdf').write_bytes(b'%PDF-1.7\nsynthetic malformed fixture\n')
manifest={'origin':'Original synthetic fixtures; no external/user document. CC0-1.0. Encryption password is public fixture-only.',
          'generation':'build_pdf_fixtures.py; reportlab invariant text fixtures. pypdf encryption includes randomness; encrypted file SHA pins this committed artifact, not deterministic regeneration.',
          'fixtures':[{'path':p.name,'sha256':sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(root.glob('*.pdf'))]}
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('generated',len(manifest['fixtures']),'original PDF fixtures')
