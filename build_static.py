"""Build a static bundle; /tr/ and /en/ remain canonical no-JS fallback pages.

Compile their copy once, rather than downloading/reparsing another document
when the visitor changes language. Preserve editable source and game files.
"""
from pathlib import Path
from html.parser import HTMLParser
import ast
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / '_site'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
ATTRS = {'aria-label','placeholder','title','alt'}


class CopyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [{'tag':'document','path':(),'children':{},'text':0}]
        self.texts = {}
        self.attributes = {}
        self.meta = {'title':'','description':''}

    def handle_starttag(self, tag, attributes):
        parent = self.stack[-1]
        parent['children'][tag] = parent['children'].get(tag,0)+1
        path = parent['path'] + ((tag,parent['children'][tag]),)
        attrs = dict(attributes)
        if tag == 'meta' and attrs.get('name') == 'description':
            self.meta['description'] = attrs.get('content','')
        if any(frame['tag']=='body' for frame in self.stack):
            for name in ATTRS:
                if attrs.get(name): self.attributes[(path,name)] = attrs[name]
        if tag not in VOID:
            self.stack.append({'tag':tag,'path':path,'children':{},'text':0})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index]['tag']==tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        tags = {frame['tag'] for frame in self.stack}
        if 'title' in tags:self.meta['title'] += value
        if 'body' not in tags or tags & {'script','style','noscript','textarea','code','pre'} or not value.strip():return
        frame=self.stack[-1]
        key=(frame['path'],frame['text'])
        frame['text']+=1
        self.texts[key]=' '.join(value.split())


def legacy_pairs(variable):
    # The old unused runtime contains useful approved dynamic labels. Read
    # literal string pairs as DATA only; never execute/import the old runtime.
    path=ROOT/'language-switcher.js'
    if not path.exists():return {}
    text=path.read_text(encoding='utf-8')
    block=re.search(r'const '+re.escape(variable)+r'\s*=\s*\{(.*?)\n  \};',text,re.S)
    if not block:return {}
    token=r'''(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")'''
    pairs={}
    for key,value in re.findall('('+token+')\\s*:\\s*('+token+')',block[1],re.S):
        try:pairs[ast.literal_eval(key)]=ast.literal_eval(value)
        except (ValueError,SyntaxError):continue
    return pairs


def build():
    tr,en=CopyParser(),CopyParser()
    tr.feed((ROOT/'tr/index.html').read_text(encoding='utf-8'))
    en.feed((ROOT/'en/index.html').read_text(encoding='utf-8'))
    texts=legacy_pairs('TR_TO_EN')
    attributes=legacy_pairs('ATTR_TR_TO_EN')
    for key,value in tr.texts.items():
        if key in en.texts and value!=en.texts[key]:texts[value]=en.texts[key]
    for key,value in tr.attributes.items():
        if key in en.attributes and value!=en.attributes[key]:attributes[value]=en.attributes[key]
    if texts.get('Hakkımızda')!='About' or len(texts)<100:
        raise RuntimeError('Native page copy alignment failed; review before publishing.')
    data={'text':list(texts.items()),'attributes':list(attributes.items()),'meta':{'tr':tr.meta,'en':en.meta}}
    if OUTPUT.exists():shutil.rmtree(OUTPUT)
    excluded={'.git','.github','_site','tests','test-results','__pycache__','build_static.py'}
    OUTPUT.mkdir()
    for item in ROOT.iterdir():
        if item.name in excluded:continue
        dest=OUTPUT/item.name
        if item.is_dir():shutil.copytree(item,dest)
        elif item.is_file():shutil.copy2(item,dest)
    helper=(ROOT/'native-language-navigation.js').read_text(encoding='utf-8')
    main_script=(ROOT/'home.js').read_text(encoding='utf-8')
    old="const isEnglish = document.documentElement.lang === 'en';"
    new="let isEnglish = document.documentElement.lang === 'en';\n  window.addEventListener('esc:languagechange', () => { isEnglish = document.documentElement.lang === 'en'; });"
    if old not in main_script:raise RuntimeError('Homepage language initializer changed; review bundle adapter.')
    main_script=main_script.replace(old,new,1)
    bundled='window.ESC_LANGUAGE_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n'+helper+'\n;\n'+main_script
    (OUTPUT/'home.js').write_text(bundled,encoding='utf-8')
    revision=hashlib.sha256(bundled.encode()).hexdigest()[:16]
    pattern=re.compile(r'''(src=["'])([^"']*\bhome\.js)(?:\?[^"']*)?(["'])''')
    count=0
    for file in OUTPUT.rglob('*.html'):
        text=file.read_text(encoding='utf-8')
        updated,matches=pattern.subn(lambda m:m[1]+m[2]+'?v='+revision+m[3],text)
        if matches:
            file.write_text(updated,encoding='utf-8');count+=1
    if count<3:raise RuntimeError('Expected root, TR and EN homepage script references.')
    print(f'Compiled {len(texts)} text pairs, {len(attributes)} attribute pairs; {count} pages; bundle {revision}')


if __name__=='__main__':build()
