import markdown, os, base64, mimetypes
from weasyprint import HTML
md=open('results/ycsb_full/REPORT_YCSB_FULL.md').read()
# inline images as base64 so weasyprint finds them
import re
def repl(m):
    alt,path=m.group(1),m.group(2)
    fp=os.path.join('results/ycsb_full',path)
    if os.path.exists(fp):
        mt=mimetypes.guess_type(fp)[0] or 'image/png'
        b=base64.b64encode(open(fp,'rb').read()).decode()
        return f'![{alt}](data:{mt};base64,{b})'
    return m.group(0)
md=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',repl,md)
html=markdown.markdown(md,extensions=['tables','fenced_code'])
FONT=os.path.abspath('assets/fonts/NotoSansCJKtc.otf')
css=f'''<style>
@font-face{{font-family:'Noto';src:url('file://{FONT}');}}
body{{font-family:'Noto',sans-serif;font-size:11px;line-height:1.5;max-width:900px;margin:0 auto;padding:20px;}}
h1{{font-size:20px;border-bottom:2px solid #333;}} h2{{font-size:16px;border-bottom:1px solid #ccc;margin-top:24px;}}
h3{{font-size:13px;}} table{{border-collapse:collapse;width:100%;font-size:10px;margin:8px 0;}}
th,td{{border:1px solid #ccc;padding:4px 6px;text-align:left;}} th{{background:#f0f0f0;}}
img{{max-width:100%;margin:8px 0;}} code{{background:#f4f4f4;padding:1px 4px;}}
blockquote{{border-left:3px solid #ccc;margin:8px 0;padding:4px 12px;color:#444;background:#fafafa;}}
</style>'''
HTML(string=css+html).write_pdf('results/ycsb_full/REPORT_YCSB_FULL.pdf')
print("PDF:", os.path.getsize('results/ycsb_full/REPORT_YCSB_FULL.pdf'), "bytes")
