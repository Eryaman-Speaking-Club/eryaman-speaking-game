/* Native /tr/ and /en/ pages remain canonical and work without JavaScript.
 * This optional enhancement changes cached copy in-place, retaining forms,
 * listeners and scroll position instead of parsing a new page on each switch.
 */
(() => {
  'use strict';
  if (window.__escNativeNavigation) return;
  const data = window.ESC_LANGUAGE_DATA;
  const routes = new Set(['/', '/tr/', '/en/']);
  if (!data || !routes.has(location.pathname)) return;
  window.__escNativeNavigation = true;
  const langOf = path => path === '/en/' ? 'en' : 'tr';
  let language = langOf(location.pathname);
  const initialLanguage = language;
  const textRecords = new Map();
  const attrRecords = new Map();
  const attrs = ['aria-label', 'placeholder', 'alt', 'title'];
  const skip = 'script,style,noscript,textarea,code,pre,[contenteditable="true"],[translate="no"]';
  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
  const spaced = (raw, value) => raw.match(/^\s*/)[0] + value + raw.match(/\s*$/)[0];
  const texts = new Map(data.text.map(([tr,en]) => [normalize(tr), {tr,en}]));
  const reverse = new Map(data.text.map(([tr,en]) => [normalize(en), {tr,en}]));
  const attributes = new Map(data.attributes.map(([tr,en]) => [tr, {tr,en}]));
  const reverseAttrs = new Map(data.attributes.map(([tr,en]) => [en, {tr,en}]));
  let observer;
  let switcher;
  let metadataFrame = 0;
  const observeOptions = {childList:true, subtree:true, characterData:true, attributes:true, attributeFilter:attrs};

  // Preserve the already loaded font locale. HTML lang still changes for
  // accessibility; cached casing below follows the actual chosen language.
  if (window.CSS && CSS.supports('-webkit-locale', '"tr"')) {
    document.documentElement.style.setProperty('-webkit-locale', JSON.stringify(initialLanguage));
  }
  function bindText(node) {
    const parent = node.parentElement;
    if (!node.isConnected || !parent || parent.closest(skip)) return;
    const raw = node.nodeValue;
    if (!normalize(raw)) return;
    const known = textRecords.get(node);
    if (known && (raw === known.tr || raw === known.en)) return;
    const pair = texts.get(normalize(raw)) || reverse.get(normalize(raw));
    let record = pair ? {tr:spaced(raw,pair.tr),en:spaced(raw,pair.en)} : {tr:raw,en:raw};
    const mode = getComputedStyle(parent).textTransform;
    if (mode === 'uppercase' || mode === 'lowercase') {
      const method = mode === 'uppercase' ? 'toLocaleUpperCase' : 'toLocaleLowerCase';
      record = {tr:record.tr[method]('tr'),en:record.en[method]('en-US')};
    }
    if (pair || record.tr !== raw || record.en !== raw) textRecords.set(node,record);
    else textRecords.delete(node);
  }
  function bindAttrs(element) {
    if (!element.isConnected || element.closest(skip)) return;
    const records = attrRecords.get(element) || {};
    for (const name of attrs) {
      const raw = element.getAttribute(name);
      const old = records[name];
      if (old && (raw === old.tr || raw === old.en)) continue;
      const pair = attributes.get(raw) || reverseAttrs.get(raw);
      if (pair) records[name] = pair;
      else delete records[name];
    }
    if (Object.keys(records).length) attrRecords.set(element,records);
    else attrRecords.delete(element);
  }
  function scan(root) {
    if (!root.isConnected) return;
    if (root.nodeType === Node.TEXT_NODE) {bindText(root);return;}
    if (!(root instanceof Element) || root.closest(skip)) return;
    bindAttrs(root);
    const walker = document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{
      acceptNode(node){return node.nodeType===Node.ELEMENT_NODE && node.matches(skip) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;}
    });
    let node;
    while ((node=walker.nextNode())) {
      if(node.nodeType===Node.TEXT_NODE)bindText(node);else bindAttrs(node);
    }
  }
  function applyCopy() {
    for (const [node,pair] of textRecords) {
      if (!node.isConnected) {textRecords.delete(node);continue;}
      if (node.nodeValue!==pair[language])node.nodeValue=pair[language];
    }
    for(const [element,records] of attrRecords) {
      if(!element.isConnected){attrRecords.delete(element);continue;}
      for(const [name,pair] of Object.entries(records)) if(element.getAttribute(name)!==pair[language])element.setAttribute(name,pair[language]);
    }
  }
  function collect(changes) {
    const roots=new Set();
    for(const change of changes){
      if(change.type==='childList')change.addedNodes.forEach(node=>roots.add(node));
      else if(change.type==='characterData')roots.add(change.target);
      else bindAttrs(change.target);
    }
    for(const root of roots)scan(root);
  }
  function syncNav() {
    for(const link of switcher.querySelectorAll('a')) {
      const active=langOf(new URL(link.href).pathname)===language;
      link.classList.toggle('active',active);
      if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    }
  }
  function setLanguage(next,url,push) {
    if(next===language)return;
    const queued=observer.takeRecords();observer.disconnect();
    try {
      if(queued.length)collect(queued);
      language=next;
      document.documentElement.lang=next;
      applyCopy();syncNav();
      if(push)history.pushState({escLanguage:next},'',url);
    }finally{observer.observe(document.body,observeOptions);}
    cancelAnimationFrame(metadataFrame);
    metadataFrame=requestAnimationFrame(()=>setTimeout(()=>{
      if(data.meta[language]?.title)document.title=data.meta[language].title;
      const description=document.querySelector('meta[name="description"]');
      if(description && data.meta[language]?.description)description.content=data.meta[language].description;
      window.dispatchEvent(new CustomEvent('esc:languagechange',{detail:{language}}));
    },0));
  }
  function init() {
    switcher=document.querySelector('.esc-lang-switch');if(!switcher)return;
    scan(document.body);
    // Resolve both text layouts once before the first language interaction,
    // without a visible flash, network request, duplicate DOM or URL change.
    performance.mark('esc-language-prepare-start');
    language=initialLanguage==='tr'?'en':'tr';applyCopy();void document.body.offsetHeight;
    language=initialLanguage;applyCopy();void document.body.offsetHeight;
    performance.mark('esc-language-prepare-end');
    performance.measure('esc-language-preparation','esc-language-prepare-start','esc-language-prepare-end');
    observer=new MutationObserver(changes=>{
      observer.disconnect();
      try{collect(changes);applyCopy();}finally{observer.observe(document.body,observeOptions);}
    });
    observer.observe(document.body,observeOptions);
    const select=event=>{
      if(event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return;
      const link=event.target.closest('a');if(!link || !switcher.contains(link))return;
      const target=new URL(link.href);if(target.origin!==location.origin || !routes.has(target.pathname))return;
      event.preventDefault();
      setLanguage(langOf(target.pathname),target.pathname+target.search+location.hash,true);
    };
    switcher.addEventListener('pointerdown',event=>{if(event.isPrimary)select(event);});
    switcher.addEventListener('click',select);
    window.addEventListener('popstate',()=>{if(routes.has(location.pathname))setLanguage(langOf(location.pathname),location.href,false);});
    syncNav();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
