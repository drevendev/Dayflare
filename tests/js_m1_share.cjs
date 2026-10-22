/* Functional share/deep-link tests for the real M1 app.js in a minimal DOM VM.
 * NOT a browser or visual test; avoids all network and external packages. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const root = path.resolve(__dirname, '..');
const site = path.join(root, 'site/m1-preview');
const app = fs.readFileSync(path.join(site, 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(site, 'index.html'), 'utf8');
const bytes = fs.readFileSync(path.join(site, 'panel.json'));
const digest = html.match(/name="dayflare-sha256" content="([a-f0-9]{64})"/)[1];
const panel = html.match(/name="dayflare-panel-id" content="([^"]+)"/)[1];
const base = 'http://example.invalid/site/m1-preview/';

class Element {
  constructor(tag='div') {
    this.tagName=tag.toUpperCase(); this.value='';this.textContent='';this.disabled=false;
    this.hidden=false;this.children=[];this.attributes={};this.events={};this.className='';
    const classes=new Set();
    this.classList={toggle:(name,active)=>{if(active) classes.add(name);else classes.delete(name);}};
  }
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(name,value){this.attributes[name]=String(value);}
  addEventListener(type,fn){this.events[type]=fn;}
  focus() {this.wasFocused=true;}
}
function urlWith(options={}) {
  const url = new URL(base);
  for (const [k,v] of Object.entries(options)) url.searchParams.append(k,v);
  return url.href;
}
async function boot(url, fixture={}) {
  const els=Object.create(null);
  const ids=['status','retry','reset','compat','share-notice','share-url','edition','subject','search','copy',
    'count','intended','unresolved','coverage-breakdown','details-title','detail-help','detail-body','details','list','empty'];
  for (const id of ids) els[id]=new Element();
  els.edition.value='all';els.subject.value='all';els.empty.hidden=true;els.compat.hidden=true;
  const location = new URL(url);
  const document={
    getElementById:(id)=>{assert.ok(els[id], `Unknown ID ${id}`);return els[id];},
    querySelector:(sel)=>({content:sel.includes('dayflare-sha256')?digest:panel}),
    createElement:(tag)=>new Element(tag)
  };
  const history={replaceState:(_s,_t,next)=>{location.href=new URL(next,location.href).href;}};
  const listeners=Object.create(null);
  const body=fixture.body || bytes;
  const stats={reads:0,cancels:0,aborts:0,scheduled:0,cleared:0,requests:0};
  const size=fixture.chunkSize || 512;
  const headers=new Map(Object.entries(fixture.headers || {}));
  const fetch=async(_url, options={})=>{
    stats.requests++;
    const stall=fixture.stallAt && (!fixture.stallOnce || stats.requests===1);
    if (stall && fixture.stallAt==='fetch') return new Promise((_resolve,reject)=>{
      options.signal?.addEventListener('abort',()=>{stats.aborts++;reject(options.signal.reason);},{once:true});
    });
    return ({
    status:fixture.status || 200,
    headers:{get:name=>headers.get(name) ?? null},
    body:{getReader:()=>{
      let offset=0;
      return {
        read:async()=>{
          stats.reads++;
          if(stall && fixture.stallAt==='read') return new Promise((_resolve,reject)=>{
            options.signal?.addEventListener('abort',()=>{stats.aborts++;reject(options.signal.reason);},{once:true});
          });
          if(offset>=body.length) return {done:true};
          const end=Math.min(body.length,offset+size);
          const value=Uint8Array.from(body.subarray(offset,end));
          offset=end;
          return {done:false,value};
        },
        cancel:async()=>{stats.cancels++;},
        releaseLock:()=>{}
      };
    }}
    });
  };
  const timers=new Set();
  const schedule=(fn,ms)=>{stats.scheduled++;const id=setTimeout(fn,fixture.fastTimeout?10:ms);timers.add(id);return id;};
  const clear=(id)=>{stats.cleared++;timers.delete(id);clearTimeout(id);};
  const ctx={document,window:{addEventListener:(type,fn)=>{listeners[type]=fn;}},history,location,crypto:webcrypto,fetch,
    URL,URLSearchParams,Uint8Array,TextDecoder,AbortController,setTimeout:schedule,clearTimeout:clear,
    navigator:{clipboard:{writeText:async()=>{}}},console};
  vm.runInNewContext(app,ctx,{filename:'app.js',timeout:1000});
  for(let n=0;n<100 && String(els.count.textContent)!=='6' &&
      !String(els.status.textContent).startsWith('Fixture unavailable:');n++) await new Promise(r=>setTimeout(r,5));
  if (!fixture.expectError) assert.equal(String(els.count.textContent),'6',els.status.textContent);
  return {els,location,stats,navigate:(next)=>{location.href=new URL(next,location.href).href;assert.ok(listeners.popstate);listeners.popstate();}};
}
async function run(){
  const root=await boot(base);
  assert.equal(root.els.list.children.length,6);
  // A visible coverage ledger must not present a missing curated example as
  // zero Wikipedia interest. Check the cross-edition/subject matrix literally.
  const editionCards = root.els['coverage-breakdown'].children;
  assert.equal(editionCards.length,2,'both editions have a coverage explanation');
  assert.match(editionCards[0].children[0].textContent,/English Wikipedia/);
  assert.match(editionCards[1].children[0].textContent,/Russian Wikipedia/);
  const at = (row, index) => row.children[1].children[index].children[1].textContent;
  assert.equal(at(editionCards[0],3),'2 observed in fixture'); // English science
  assert.equal(at(editionCards[1],2),'1 observed in fixture'); // Russian games
  assert.equal(at(editionCards[0],0),'Not included'); // English culture
  assert.equal(at(editionCards[1],0),'Not included'); // Russian culture

  assert.match(root.els['share-url'].value,/sha=[0-9a-f]{64}/);
  assert.ok(root.els.compat.hidden);
  root.els.list.children[0].events.click();
  assert.match(root.els['share-url'].value,/page=en.wikipedia%3A17/);
  assert.equal(root.els['details-title'].textContent,'Example-new');
  assert.ok(root.els.details.wasFocused);
  root.els.search.value='unknown topic term';
  root.els.search.events.input();
  assert.equal(root.els.list.children.length,0);
  assert.doesNotMatch(root.els['share-url'].value,/[?&]page=/);
  const bindings={schema:'dayflare.identity-panel.v1',panel,sha:digest};
  const compatible=await boot(urlWith({...bindings,edition:'ru.wikipedia',subject:'games',page:'ru.wikipedia:62'}));
  assert.equal(compatible.els.list.children.length,1);
  assert.equal(compatible.els['details-title'].textContent,'Демо: игра');
  assert.equal(compatible.els['details-title'].attributes.lang,'ru', 'detail heading announces Russian');
  assert.equal(compatible.els.list.children[0].children[1].attributes.lang,'ru', 'card title announces Russian');
  compatible.els.search.value='unmatched'; compatible.els.search.events.input();
  assert.equal(compatible.els['details-title'].attributes.lang,'en', 'cleared detail heading resets to English');
  assert.ok(compatible.els.compat.hidden);
  for (const bad of [
    {page:'ru.wikipedia:62'},
    {...bindings,edition:'ru.wikipedia',subject:'science',page:'ru.wikipedia:62'},
    {...bindings,edition:'ru.wikipedia',query:'no matching page',page:'ru.wikipedia:62'},
    {...bindings,sha:'0'.repeat(64),page:'ru.wikipedia:62'},
    {...bindings,edition:'ru.wikipedia',unrecognized:'unexpected'},
  ]) {
    const view=await boot(urlWith(bad));
    assert.equal(view.els.compat.hidden,false,JSON.stringify(bad));
    assert.equal(view.els.list.children.length,0,JSON.stringify(bad));
    assert.match(view.els.status.textContent,/Incompatible shared view/);
    assert.equal(view.els.copy.disabled,true);
    assert.ok(view.els.reset.wasFocused,'incompatible link focuses nearby recovery action');
  }
  const duplicateURL = new URL(urlWith({...bindings,page:'ru.wikipedia:62'}));
  duplicateURL.searchParams.append('page','ru.wikipedia:801');
  const duplicate=await boot(duplicateURL.href);
  assert.equal(duplicate.els.compat.hidden,false);
  assert.equal(duplicate.els.list.children.length,0);
  duplicate.els.reset.events.click();
  assert.ok(duplicate.els.compat.hidden);
  assert.equal(duplicate.els.list.children.length,6);
  assert.equal(duplicate.els.copy.disabled,false);
  // Browser back/forward must reconstruct exactly the URL's selection and
  // reactivate controls after an incompatible link; no ghost detail is allowed.
  const traversed=await boot(urlWith({...bindings,edition:'ru.wikipedia',page:'ru.wikipedia:62'}));
  assert.equal(traversed.els['details-title'].textContent,'Демо: игра');
  traversed.navigate(urlWith({...bindings,edition:'ru.wikipedia'}));
  assert.equal(traversed.els['details-title'].textContent,'Choose a page');
  assert.equal(traversed.els['detail-body'].children.length,0);
  assert.equal(traversed.els.list.children.some(card => card.attributes['aria-pressed']==='true'),false);
  assert.doesNotMatch(traversed.els['share-url'].value,/[?&]page=/);
  traversed.navigate(urlWith({...bindings,sha:'0'.repeat(64)}));
  assert.equal(traversed.els.compat.hidden,false);
  assert.equal(traversed.els.copy.disabled,true);
  traversed.navigate(urlWith({...bindings,edition:'ru.wikipedia',page:'ru.wikipedia:62'}));
  assert.equal(traversed.els.compat.hidden,true);
  assert.equal(traversed.els.copy.disabled,false);
  assert.equal(traversed.els.edition.disabled,false);
  assert.equal(traversed.els['details-title'].textContent,'Демо: игра');
  assert.equal(traversed.els.list.children.filter(card => card.attributes['aria-pressed']==='true').length,1);
  traversed.navigate(urlWith({...bindings,edition:'ru.wikipedia'}));
  assert.equal(traversed.els['details-title'].textContent,'Choose a page');
  assert.doesNotMatch(traversed.els['share-url'].value,/[?&]page=/);
  const cleared=await boot(urlWith({...bindings,edition:'ru.wikipedia',query:'no match'}));
  assert.ok(cleared.els.compat.hidden);
  assert.equal(cleared.els.list.children.length,0);
  assert.equal(cleared.els.empty.hidden,false);
  const expectBlocked=async (fixture, message)=>{
    const view=await boot(base,{...fixture,expectError:true});
    assert.match(view.els.status.textContent,message);
    assert.equal(view.els.copy.disabled,true);
    assert.equal(view.els.retry.hidden,false);
    assert.equal(view.els.list.children.length,0);
    assert.equal(view.els.count.textContent,'—');
    assert.equal(view.els['coverage-breakdown'].children.length,1);
    assert.match(view.els['coverage-breakdown'].children[0].textContent,/Coverage unavailable/);
    return view;
  };
  const beforeRead=await expectBlocked({headers:{'content-length':String(300000)}},/transfer size cap/);
  assert.equal(beforeRead.stats.reads,0,'reject oversized declared bodies before reading');
  await expectBlocked({headers:{'content-length':'1x'}},/invalid Content-Length/);
  const oversized=await expectBlocked({body:Buffer.alloc(300000),chunkSize:65536},/decoded size cap/);
  assert.ok(oversized.stats.reads<7,'stop reading overbudget response');
  assert.equal(oversized.stats.cancels,1,'cancel overbudget stream');
  await expectBlocked({headers:{'content-length':String(bytes.length-1)}},/mismatched Content-Length/);
  await expectBlocked({headers:{'content-length':String(bytes.length+5)}},/mismatched Content-Length/);
  await expectBlocked({body:Buffer.from('{\"tampered\":true}')},/SHA-256 mismatch/);
  // Stalled requests and stalled body streams must resolve into an actionable
  // retry state within the fixture deadline, never an indefinite spinner.
  const stalledFetch=await expectBlocked({stallAt:'fetch',fastTimeout:true},/fixture request timed out/);
  assert.equal(stalledFetch.stats.aborts,1,'deadline aborts a stalled fetch');
  const stalledBody=await expectBlocked({stallAt:'read',fastTimeout:true},/fixture request timed out/);
  assert.equal(stalledBody.stats.aborts,1,'deadline aborts a stalled response stream');
  assert.equal(stalledBody.stats.cleared,1,'deadline is cleared after failure');
  const recovering=await expectBlocked({stallAt:'fetch',stallOnce:true,fastTimeout:true},/fixture request timed out/);
  recovering.els.retry.events.click();
  for(let i=0;i<50 && recovering.els.count.textContent!=='6';i++)
    await new Promise(r=>setTimeout(r,5));
  assert.equal(String(recovering.els.count.textContent),'6','retry loads the validated fixture');
  assert.equal(recovering.els.list.children.length,6);
  assert.equal(recovering.els['coverage-breakdown'].children.length,2);
  assert.equal(recovering.els.copy.disabled,false);
  assert.equal(recovering.els.retry.hidden,true);
  assert.equal(recovering.stats.requests,2);

  const compressed=await boot(base,{headers:{'content-encoding':'gzip','content-length':'120'}});
  assert.equal(compressed.els.list.children.length,6,'compressed transfer lengths are not decoded-body lengths');
  console.log('PASS M1 VM: history traversal, ghost-selection reset, incompatible-link recovery, bounded streamed fixture, stalled fetch/body timeout, tamper; NO browser, NO network');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
