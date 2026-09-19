"""Real mouse/touch language interaction with passive next-frame timing.

The static /tr/ and /en/ pages remain fallback routes; enhanced changes must
not create a new document. TEST_BASE_URL selects the deployed production site.
"""
import functools,json,os,threading
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results';OUT.mkdir(exist_ok=True)
ENGINE=os.environ.get('ENGINE','webkit')
MOBILE=os.environ.get('MOBILE','false')=='true'
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',8768),functools.partial(Quiet,directory=str(ROOT/'_site')))
threading.Thread(target=server.serve_forever,daemon=True).start()
BASE=os.environ.get('TEST_BASE_URL','http://127.0.0.1:8768/')
PROBE=r'''() => {
 window.__testDocumentId=crypto.randomUUID();window.samples=[];window.frames=[];
 let previous=performance.now();
 function frame(now){if(samples.length)frames.push(now-previous);previous=now;requestAnimationFrame(frame)}requestAnimationFrame(frame);
 document.addEventListener('pointerdown',event=>{
  const link=event.target.closest('.esc-lang-switch a');if(!link)return;
  const sample={from:document.documentElement.lang,to:link.getAttribute('href'),start:performance.now()};samples.push(sample);
  requestAnimationFrame(()=>setTimeout(()=>{
   sample.toPaintMs=performance.now()-sample.start;
   sample.language=document.documentElement.lang;
   sample.path=location.pathname;
   sample.menu=document.querySelector('.nav-links a').innerText;
   sample.heroOpacity=parseFloat(getComputedStyle(document.querySelector('.hero-copy')).opacity);
  },0));
 },true);
}'''
result={'engine':ENGINE,'mobile':MOBILE,'baseUrl':BASE,'samples':[],'errors':[],'documentRequests':[]}
with sync_playwright() as p:
 b=getattr(p,ENGINE).launch()
 c=b.new_context(viewport={'width':390 if MOBILE else 1440,'height':844 if MOBILE else 950},is_mobile=MOBILE,has_touch=MOBILE)
 page=c.new_page();page.set_default_timeout(12000)
 page.on('pageerror',lambda error:result['errors'].append(str(error)))
 try:
  page.goto(BASE,wait_until='domcontentloaded',timeout=30000)
  page.wait_for_timeout(1200)
  result['initialUrl']=page.url
  assert page.evaluate('Boolean(window.ESC_LANGUAGE_DATA && window.__escNativeNavigation)'),'New compiled language bundle missing'
  result['preparationMs']=page.evaluate('performance.getEntriesByName("esc-language-preparation").map(e=>e.duration)')
  page.evaluate(PROBE)
  identity=page.evaluate('window.__testDocumentId')
  before=page.locator('*').count()
  page.on('request',lambda request:result['documentRequests'].append(request.url) if request.is_navigation_request() and request.frame==page.main_frame else None)
  for lang in ['en','tr']*12:
   link=page.locator('.esc-lang-switch a[href="/'+lang+'/"]')
   link.tap() if MOBILE else link.click()
   sample=None
   for _ in range(40):
    page.wait_for_timeout(50)
    sample=page.evaluate('window.samples?.[window.samples.length-1] || null')
    if sample and 'toPaintMs' in sample:break
   assert sample and 'toPaintMs' in sample,'No frame sample / document replaced'
   result['samples'].append(sample)
   assert sample['language']==lang and sample['path']=='/'+lang+'/',sample
   assert sample['menu']==('About' if lang=='en' else 'Hakkımızda'),sample
   assert sample['heroOpacity']>.99,sample
   assert sample['toPaintMs']<250,'Slow language response: '+str(sample)
   assert page.evaluate('window.__testDocumentId')==identity,'Document was reloaded'
   assert link.get_attribute('aria-current')=='page'
   page.wait_for_timeout(70)
  result['beforeNodes']=before;result['afterNodes']=page.locator('*').count()
  assert before==result['afterNodes'],'DOM grows while switching'
  assert not result['documentRequests'],'Language changes request new HTML documents'
  page.wait_for_timeout(700)
  result['maxFrameGapMs']=page.evaluate('Math.max(...window.frames)')
  assert result['maxFrameGapMs']<300,'Delayed frame freeze after switching'
  # Both English and Turkish visible casing, including dynamically added text.
  for lang in ['en','tr']:
   page.locator('.esc-lang-switch a[href="/'+lang+'/"]').click()
   page.wait_for_timeout(80)
   case=page.evaluate('''async () => {
    const box=document.createElement('div');box.style.cssText='position:absolute;left:-10000px';
    box.innerHTML='<span style="text-transform:uppercase">indigo science</span><span style="text-transform:lowercase">INDIGO SCIENCE</span>';
    document.body.appendChild(box);await new Promise(resolve=>requestAnimationFrame(resolve));
    const values=[...box.children].map(n=>n.innerText);box.remove();return values;
   }''')
   expected=['INDIGO SCIENCE','indigo science'] if lang=='en' else ['İNDİGO SCİENCE','ındıgo scıence']
   assert case==expected,{'lang':lang,'casing':case}
  page.evaluate('history.back()');page.wait_for_timeout(200)
  assert page.evaluate('document.documentElement.lang')=='en'
  assert page.evaluate('window.__testDocumentId')==identity
  page.screenshot(path=str(OUT/(ENGINE+('-mobile' if MOBILE else '-desktop')+'-en.png')))
  if MOBILE:page.locator('.menu-btn').click()
  page.locator('.nav-links a[href="#faq"]').click();page.wait_for_timeout(900)
  assert page.locator('#faq h2').is_visible()
  assert not result['errors'],result['errors']
  result['passed']=True
 except Exception as error:
  result['passed']=False;result['failure']=str(error)
 finally:
  print(json.dumps(result),flush=True)
  (OUT/'static-language-results.json').write_text(json.dumps(result,indent=2))
  b.close()
server.shutdown()
assert result['passed'],'See static-language-results.json'
