/* Dayflare M0: read-only historical evidence explorer. No live API or data mutation. */
(() => {
  'use strict';
  const DATASET = 'd02-20261018-084126';
  const METHOD = 'v0-empirical-35d';
  const ZIP_URL = '../evidence/d02-20261018/source.zip';
  const ZIP_SHA = '3fe9070340da79f93b96f8bba1b60d809bc0e8b948a042039af87fb50955d631';
  const MEMBERS = {
    'sample.json': '98880f706c0d8b5433f0fbb46bcad0cb9a2d515ea894752dcd971326e5805a8e',
    'receipt.json': '298c6ade24ec911502f4e2bee23e4c3ac012eecc8192b56071210d3cf94adb21'
  };
  const $ = id => document.getElementById(id);
  // The source preview has no local m1/ directory. Preserve a usable HTML
  // download in the markup; only the published repository root serves m1/.
  const latestAtlas = $('latest-atlas');
  if (latestAtlas && location.hostname === 'drevendev.github.io' &&
      /^\/Dayflare\/(?:index\.html)?$/.test(location.pathname)) {
    latestAtlas.setAttribute('href', 'm1/');
    const label = $('latest-atlas-label');
    if (label) label.textContent = 'Explore latest M1 atlas';
  }
  const ui = ['edition','subject','query','order','compare-select','copy','clear'].map($);
  const fmt = new Intl.NumberFormat('en-US', {maximumFractionDigits: 1});
  let series = [], selected = null, compared = null, loaded = false, incompatible = false;
  let shareEpoch = 0; // Invalidate pending clipboard responses when the view or request changes.
  const fail = msg => {throw new Error(msg)};
  function status(msg, bad=false) { $('status').textContent=msg; $('status').classList.toggle('error',bad); }
  function hex(buffer) {return Array.from(new Uint8Array(buffer), b=>b.toString(16).padStart(2,'0')).join('');}
  async function digest(bytes) {return hex(await crypto.subtle.digest('SHA-256', bytes));}
  async function readZip(bytes) {
    if(bytes.byteLength<32 || bytes.byteLength>512*1024) fail('Snapshot archive exceeds the allowed size.');
    if(await digest(bytes)!==ZIP_SHA) fail('Snapshot checksum does not match the reviewed evidence.');
    const view=new DataView(bytes), decoder=new TextDecoder('utf-8',{fatal:true}), files={};
    let offset=0;
    while(offset+4<=bytes.byteLength && view.getUint32(offset,true)===0x04034b50) {
      if(offset+30>bytes.byteLength) fail('Incomplete ZIP entry header.');
      const flags=view.getUint16(offset+6,true),method=view.getUint16(offset+8,true),packed=view.getUint32(offset+18,true),size=view.getUint32(offset+22,true),nameLen=view.getUint16(offset+26,true),extraLen=view.getUint16(offset+28,true);
      if(flags&0x08 || flags&0x01 || method!==8 || size>128*1024 || packed>128*1024) fail('Unsupported or oversized ZIP member.');
      const nameEnd=offset+30+nameLen, start=nameEnd+extraLen, end=start+packed;
      if(end>bytes.byteLength) fail('Incomplete ZIP member.');
      const name=decoder.decode(new Uint8Array(bytes,offset+30,nameLen));
      if(!(name in MEMBERS) || files[name]) fail('Unexpected or duplicated ZIP member.');
      if(!('DecompressionStream' in window)) fail('This browser cannot read the offline evidence archive.');
      const stream=new Blob([new Uint8Array(bytes,start,packed)]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      // A small compressed ZIP can expand far beyond its declared length.
      // Bound inflation *before* allocating the complete member or parsing JSON.
      const reader=stream.getReader(), chunks=[];
      let inflated=0;
      try {
        while(true) {
          const {done,value}=await reader.read();
          if(done) break;
          inflated+=value.byteLength;
          if(inflated>size || inflated>128*1024) {
            await reader.cancel();
            fail('Decompressed ZIP member exceeds its declared size or safety limit.');
          }
          chunks.push(value);
        }
      } finally {reader.releaseLock();}
      if(inflated!==size) fail('Incomplete ZIP member.');
      const raw=new Uint8Array(inflated);
      let copied=0;
      for(const chunk of chunks){raw.set(chunk,copied);copied+=chunk.byteLength;}
      if(await digest(raw)!==MEMBERS[name]) fail('Invalid ZIP member checksum.');
      files[name]=JSON.parse(decoder.decode(raw));
      offset=end;
    }
    if(Object.keys(files).length!==2 || !files['sample.json'] || !files['receipt.json']) fail('Required evidence members missing.');
    return files;
  }
  // Browser-side limits complement, but never replace, validated release bytes.
  // Refuse an unbounded/stalled response before allocating a full archive.
  const ZIP_LIMIT=512*1024, ZIP_TIMEOUT_MS=12000;
  async function downloadZip() {
    const controller=new AbortController();
    let timedOut=false;
    const timer=setTimeout(()=>{timedOut=true;controller.abort();},ZIP_TIMEOUT_MS);
    try {
      const response=await fetch(ZIP_URL,{cache:'no-store',signal:controller.signal});
      if(!response.ok) fail(`Evidence unavailable (HTTP ${response.status}).`);
      const length=response.headers.get('Content-Length');
      if(length!==null && (!/^(0|[1-9]\d*)$/.test(length) || Number(length)>ZIP_LIMIT))
        fail('Snapshot archive exceeds the allowed size.');
      if(!response.body)fail('Streaming evidence download is unavailable in this browser.');
      const reader=response.body.getReader(), parts=[];
      let size=0;
      while(true) {
        const {done,value}=await reader.read();
        if(done)break;
        size+=value.byteLength;
        if(size>ZIP_LIMIT) {
          await reader.cancel();
          fail('Snapshot archive exceeds the allowed size.');
        }
        parts.push(value);
      }
      // Browsers decode HTTP Content-Encoding transparently; only compare
      // declared wire length when the delivered representation is identity.
      if(length!==null && !response.headers.get('Content-Encoding') && size!==Number(length))
        fail('Incomplete snapshot transfer.');
      const raw=new Uint8Array(size);
      let pos=0;
      for(const part of parts){raw.set(part,pos);pos+=part.byteLength;}
      return raw.buffer;
    } catch(error) {
      if(timedOut) fail('Snapshot request exceeded the time limit.');
      throw error;
    } finally {clearTimeout(timer);}
  }
  function safeCount(v) {return Number.isSafeInteger(v) && v>=0;}
  function verifyEvidence(files) {
    const sample=files['sample.json'], receipt=files['receipt.json'];
    if(!Array.isArray(sample) || sample.length!==6 || !receipt.success || receipt.schema_version!==1 || receipt.method_version!==METHOD || receipt.request_count!==6 || !Array.isArray(receipt.series_metrics) || receipt.series_metrics.length!==6) fail('Evidence schema or method is incompatible.');
    if(receipt.observation_window?.start!=='20260811' || receipt.observation_window?.end!=='20260914' || receipt.observation_window.expected_days!==35) fail('Unexpected observation window.');
    const rows=[];
    for(let i=0;i<6;i++) {
      const request=receipt.series_metrics[i].request, metric=receipt.series_metrics[i].metrics;
      const obs=sample[i].items;
      const edition=request?.project, article=request?.article;
      if(!['en.wikipedia.org','ru.wikipedia.org'].includes(edition) || typeof article!=='string' || !article || !Array.isArray(obs) || obs.length!==35 || !metric) fail('Evidence series unavailable.');
      const seen=new Set();
      for(let j=0;j<35;j++) {
        const row=obs[j];
        if(!safeCount(row.views) || row.project!==edition.replace('.org','') || row.article!==article || row.value_state!=='observed' || row.agent!=='user' || row.access!=='all-access' || row.granularity!=='daily' || !/^2026-\d\d-\d\d$/.test(row.date) || seen.has(row.date)) fail('Invalid daily observation.');
        const expected=new Date(Date.UTC(2026,7,11+j)).toISOString().slice(0,10);
        if(row.date!==expected) fail('Incomplete or misordered history.');
        seen.add(row.date);
      }
      const weeks=Array.from({length:5},(_,j)=>obs.slice(j*7,(j+1)*7).reduce((sum,x)=>sum+x.views,0));
      const baseline=[...weeks.slice(0,4)].sort((a,b)=>a-b);
      const median=(baseline[1]+baseline[2])/2, latest=weeks[4], delta=latest-median;
      if(weeks.some((v,j)=>v!==metric.weekly_totals_oldest_to_current[j]) || metric.V!==latest || metric.B!==median || metric.delta!==delta || (median===0 ? metric.relative_lift!==null : Math.abs(metric.relative_lift-delta/median)>1e-10)) fail('Reported weekly calculation differs from observations.');
      rows.push({id:`${DATASET}:${i}`,index:i,edition,article,subject:request.subject,items:obs,weekly:weeks,latest,median,delta,relative:median===0?null:delta/median});
    }
    return rows;
  }
  const name = s => s.article.replaceAll('_',' ');
  const n = x => fmt.format(x);
  function signed(x) {return `${x<0?'−':'+'}${n(Math.abs(x))}`;}
  function percentage(x) {if(x===null) return 'Unavailable (zero baseline)'; const p=Math.abs(x)*100; return `${x<0?'−':'+'}${p<0.05 && p>0?p.toFixed(3):p.toFixed(1)}%`;}
  const editionName = s => s.edition.startsWith('en')?'EN · English':'RU · Русский';
  const subjectName = v => ({'science/technology':'Science & technology','culture/literature':'Literature','games/sport':'Games & sport'})[v]||'Other';
  function element(tag,cls,text) {const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
  function resetShareFallback() {shareEpoch++;$('share-fallback').hidden=true;$('share-url').value='';}
  function setEnabled(ready) {ui.forEach(x=>x.disabled=!ready);$('copy').disabled=!ready||selected===null;$('compare-select').disabled=!ready||selected===null;}
  // Sorting is descriptive only, not a trend or lifecycle classification. The
  // source-position tie-breaker makes URLs and UI order deterministic.
  const ORDERINGS = ['magnitude','increase','decrease','volume','source'];
  function filtered() {
    const rows=series.filter(s=>($('edition').value==='all'||$('edition').value===s.edition)&&($('subject').value==='all'||$('subject').value===s.subject)&&name(s).toLocaleLowerCase().includes($('query').value.trim().toLocaleLowerCase()));
    const order=$('order').value;
    const metric = s => order==='magnitude' ? Math.abs(s.delta)
      : order==='increase'||order==='decrease' ? s.delta
      : order==='volume' ? s.latest : -s.index;
    // A baseline-median comparison yields half-view deltas; ordering uses
    // exactly those measured numeric values rather than displayed rounding.
    rows.sort((a,b)=>(order==='decrease' ? metric(a)-metric(b) : metric(b)-metric(a)) || a.index-b.index);
    return rows;
  }
  function renderCards() {
    $('cards').replaceChildren(); const rows=filtered();$('empty').hidden=rows.length!==0;
    for(const s of rows) {
      const card=element('button','card');card.type='button';card.setAttribute('aria-pressed',String(selected===s.index));
      card.append(element('span','tag',`${editionName(s)} · ${subjectName(s.subject)}`), element('h3','',name(s)));
      const stats=element('div','numbers'); const left=element('div');left.append(element('strong',`delta${s.delta<0?' negative':''}`,percentage(s.relative)),element('div','small',`${signed(s.delta)} vs. baseline`));const right=element('div','small',`${n(s.latest)} views\nlast 7 days`);right.style.whiteSpace='pre-line';stats.append(left,right);card.append(stats);
      card.addEventListener('click',()=>select(s.index,true)); $('cards').append(card);
    }
    if(!rows.length) status('No matches in this six-series sample.');else status(`${rows.length} of 6 measured series. Snapshot is historical, not live.`);
  }
  function metric(value,title) {const d=element('div','metric');d.append(element('strong','',value),element('span','',title));return d;}
  function chart(s) {
    const svg=$('spark');while(svg.lastChild && !['title','desc'].includes(svg.lastChild.localName))svg.removeChild(svg.lastChild);
    const points=s.items.map(x=>x.views), min=Math.min(...points), max=Math.max(...points), span=Math.max(1,max-min);
    const path=points.map((x,i)=>`${i?'L':'M'}${16+i*588/34},${128-(x-min)/span*105}`).join(' ');
    const node=document.createElementNS('http://www.w3.org/2000/svg','path');node.setAttribute('d',path);node.setAttribute('fill','none');node.setAttribute('stroke','#b04022');node.setAttribute('stroke-width','3');node.setAttribute('stroke-linecap','round');svg.append(node);
    $('spark-title').textContent=`Daily pageviews for ${name(s)}`;
    $('spark-description').textContent=`35 observed daily values from 11 August to 14 September 2026. Minimum ${n(min)}; maximum ${n(max)}. Exact table below.`;
  }
  function select(index,writeHistory) {
    const s=series[index];if(!s)return;
    selected=index;compared=compared===index?null:compared;setEnabled(true);
    $('detail').hidden=false;$('comparison').hidden=false;$('detail-title').textContent=name(s);
    $('detail-info').textContent=`${editionName(s)} · ${subjectName(s.subject)} · 35 complete UTC days · stable identity across snapshots NOT verified`;
    $('detail-summary').replaceChildren(metric(n(s.latest),'8–14 September · pageviews'),metric(n(s.median),'Median of 4 previous weeks'),metric(signed(s.delta),'Absolute weekly change'),metric(percentage(s.relative),'Relative change vs. baseline'));
    chart(s);
    $('history-disclosure').open=false;
    const history=$('history');history.replaceChildren();for(const row of s.items){const tr=element('tr');const dateHeader=element('th','',row.date);dateHeader.scope='row';tr.append(dateHeader,element('td','',n(row.views)));history.append(tr);}
    $('article').href=`https://${s.edition}/wiki/${encodeURIComponent(s.article)}`;
    const choices=$('compare-select');choices.replaceChildren(new Option('Choose a second page',''));
    for(const other of series)if(other.index!==index)choices.add(new Option(`${editionName(other)} — ${name(other)}`,String(other.index)));
    choices.value=compared===null?'':String(compared);renderCards();renderCompare();if(writeHistory){share(true);$('detail-title').focus();}
  }
  // Clipboard feedback is only valid for the URL it described. Any subsequent
  // filter/selection/navigation resets it to this neutral context message.
  const shareHint = () => compared===null
    ? 'Choose a second series to compare equivalent windows. No cross-edition identity equivalence is assumed.'
    : 'Count comparison only. Different pages or editions do not imply matched entities, populations, or causation.';
  function renderCompare() {
    resetShareFallback();
    const host=$('compare-table'), dailyHost=$('compare-daily');
    host.replaceChildren();dailyHost.replaceChildren();
    $('share-state').textContent=shareHint();
    if(selected===null||compared===null)return;
    const a=series[selected],b=series[compared];
    const t=element('table');
    t.append(element('caption','',`${name(a)} / ${name(b)} — matched UTC weeks`));
    const head=element('thead'),hr=element('tr');
    for(const v of ['Window',`${name(a)} (${a.edition.startsWith('en')?'EN':'RU'})`,`${name(b)} (${b.edition.startsWith('en')?'EN':'RU'})`]) {
      const th=element('th','',v);th.scope='col';hr.append(th);
    }
    head.append(hr);t.append(head);
    const body=element('tbody');
    for(let i=0;i<5;i++) {
      const tr=element('tr');
      const windowHeader=element('th','',`${i===4?'Latest':'Baseline'} week ${i+1} · ${a.items[7*i].date}–${a.items[7*i+6].date}`);windowHeader.scope='row';tr.append(windowHeader,element('td','',n(a.weekly[i])),element('td','',n(b.weekly[i])));
      body.append(tr);
    }
    t.append(body);host.append(t);
    // Weekly totals can hide different day-by-day patterns. Let a reader
    // inspect both complete source histories without switching topics.
    const details=element('details','history-disclosure');
    details.append(element('summary','','Inspect 35 exact daily values side by side (UTC)'));
    details.append(element('p','fine','Dates are UTC. On narrow screens, scroll the table horizontally to inspect both page counts.'));
    const wrap=element('div','tablewrap'),days=element('table');
    wrap.tabIndex=0;
    wrap.setAttribute('role','region');
    wrap.setAttribute('aria-label','Daily pageviews for both measured Wikipedia series; scroll horizontally if needed');
    days.append(element('caption','',`${name(a)} / ${name(b)} — 2026-08-11 to 2026-09-14, daily Wikipedia pageviews`));
    const dayHead=element('thead'),dayRow=element('tr');
    for(const v of ['UTC date',`${name(a)} (${a.edition.startsWith('en')?'EN':'RU'})`,`${name(b)} (${b.edition.startsWith('en')?'EN':'RU'})`]) {
      const th=element('th','',v);th.scope='col';dayRow.append(th);
    }
    dayHead.append(dayRow);days.append(dayHead);
    const dayBody=element('tbody');
    for(let i=0;i<35;i++) {
      const tr=element('tr');
      const dateHeader=element('th','',a.items[i].date);dateHeader.scope='row';tr.append(dateHeader,element('td','',n(a.items[i].views)),element('td','',n(b.items[i].views)));
      dayBody.append(tr);
    }
    days.append(dayBody);wrap.append(days);details.append(wrap);dailyHost.append(details);
  }

  function viewUrl() {const u=new URL(window.location.href);u.search='';u.hash=selected===null?'#discover':compared===null?'#detail':'#comparison';u.searchParams.set('ds',DATASET);u.searchParams.set('m',METHOD);u.searchParams.set('w','20260811-20260914');if(selected!==null){u.searchParams.set('s',String(selected));u.searchParams.set('ed',series[selected].edition);}if(compared!==null)u.searchParams.set('c',String(compared));if($('edition').value!=='all')u.searchParams.set('e',$('edition').value);if($('subject').value!=='all')u.searchParams.set('sub',$('subject').value);if($('query').value)u.searchParams.set('q',$('query').value);if($('order').value!=='magnitude')u.searchParams.set('o',$('order').value);return u.toString();}
  function share(writeHistory) {
    if(!loaded || incompatible)return;
    resetShareFallback();
    $('share-state').textContent=shareHint();
    const link=viewUrl();
    // Selecting a topic is a new navigation step; typing/filtering and Clear
    // update this step in place. Otherwise a stale URL resurrects the empty
    // filter after reload and copied discover links lose their context.
    if(writeHistory)history.pushState({},'',link);
    else history.replaceState({},'',link);
    return link;
  }
  function rejectSharedLink(message) {
    resetShareFallback();
    // A stale detail is particularly misleading after browser Back/Forward: never
    // leave the previously selected page visible under an incompatible deep link.
    incompatible=true;
    selected=null;
    compared=null;
    setEnabled(false);
    $('cards').replaceChildren();
    $('empty').hidden=true;
    $('detail').hidden=true;
    $('comparison').hidden=true;
    $('detail-summary').replaceChildren();
    $('history').replaceChildren();
    $('compare-table').replaceChildren();
    $('compare-daily').replaceChildren();
    $('share-state').textContent='';
    $('retry').textContent='Clear incompatible link';
    $('retry').hidden=false;
    status(message,true);
  }
  function restore(fromLoad=false) {
    const p=new URL(location.href).searchParams;
    // An unversioned deep link must never silently attach its old selection to
    // the current archive. Bare landing-page URLs remain valid.
    const versionKeys=['ds','m','w'];
    const savedKeys=[...versionKeys,'s','c','ed','e','sub','q','o'];
    // URLSearchParams.get() silently chooses the *first* of repeated keys.
    // Do not restore ambiguous dataset/selection/filter state from such links.
    if(savedKeys.some(k=>p.getAll(k).length>1)) {
      rejectSharedLink('Shared view has repeated dataset, method, selection or filter parameters. Clear the link to recover.');
      return;
    }
    if(savedKeys.some(k=>p.has(k)) && versionKeys.some(k=>!p.has(k))) {
      rejectSharedLink('Shared view lacks an exact dataset, method or observation window. No data was silently substituted.');
      return;
    }
    if((p.has('ds')&&p.get('ds')!==DATASET)||(p.has('m')&&p.get('m')!==METHOD)||(p.has('w')&&p.get('w')!=='20260811-20260914')) {
      rejectSharedLink('This shared link targets a different dataset or method. No data has been silently substituted.');
      return;
    }
    // A previously selected topic must not remain on screen for malformed
    // edition, subject, series or comparison parameters during navigation.
    for(const [key,id,possible] of [['e','edition',['all','en.wikipedia.org','ru.wikipedia.org']],['sub','subject',['all','science/technology','culture/literature','games/sport']]]) {
      const value=p.get(key);
      if(value!==null&&!possible.includes(value)) {
        rejectSharedLink(`Unknown ${key==='e'?'edition':'subject'} filter in shared link. Reset to recover.`);
        return;
      }
      $(id).value=value===null?'all':value;
    }
    const order=p.get('o')||'magnitude';
    if(!ORDERINGS.includes(order)) {
      rejectSharedLink('Unknown discovery ordering in shared link. Clear the link to recover.');
      return;
    }
    $('order').value=order;
    $('query').value=p.get('q')||'';
    const s=p.get('s'),c=p.get('c');
    if(s!==null&&!/^[0-5]$/.test(s)) {
      rejectSharedLink('Unknown series in shared link. Choose to reset the view.');
      return;
    }
    const si=s===null?null:Number(s);
    if(p.has('ed')&&(si===null||series[si].edition!==p.get('ed'))) {
      rejectSharedLink('Shared-link edition is incompatible with the recorded series.');
      return;
    }
    if(c!==null&&(si===null||!/^[0-5]$/.test(c)||Number(c)===si)) {
      rejectSharedLink('Incompatible comparison selection; the view cannot be restored.');
      return;
    }
    incompatible=false;
    setEnabled(true);
    selected=si;compared=c===null?null:Number(c);$('retry').hidden=true;renderCards();if(si===null){$('detail').hidden=true;$('comparison').hidden=true;}else select(si,false);
    // A shared deep link can target a section hidden until asynchronous evidence
    // validation finishes. Initial fragment scrolling then happens too early.
    // Restore the visible destination and keyboard focus after rendering, but
    // leave ordinary browser Back/Forward scroll restoration untouched.
    if(fromLoad && si!==null) {
      const target = compared===null ? 'detail' : 'comparison';
      if(location.hash===`#${target}`) requestAnimationFrame(()=>{
        if(!loaded || incompatible || selected!==si || location.hash!==`#${target}`)return;
        const heading=$(target==='detail'?'detail-title':'compare-title');
        heading.focus({preventScroll:true});
        heading.scrollIntoView({block:'start',behavior:'auto'});
      });
    }
  }
  async function load() {
    resetShareFallback();
    loaded=false;incompatible=false;series=[];selected=null;compared=null;setEnabled(false);$('cards').replaceChildren();$('empty').hidden=true;$('detail').hidden=true;$('comparison').hidden=true;$('retry').hidden=true;status('Loading and verifying the historical snapshot…');
    try {
      const raw=await downloadZip();const data=await readZip(raw);series=verifyEvidence(data);loaded=true;restore(true);
    }catch(e){status(`${e.message} No measured data is displayed.`,true);$('retry').textContent='Retry loading the retained snapshot';$('retry').hidden=false;setEnabled(false);}
  }
  for(const id of ['edition','subject','query','order'])$(id).addEventListener(id==='query'?'input':'change',()=>{if(!loaded||incompatible)return;renderCards();share(false);});
  $('compare-select').addEventListener('change',e=>{if(!loaded||incompatible)return;compared=e.target.value===''?null:Number(e.target.value);renderCompare();share(true);});
  $('copy').addEventListener('click',async()=>{
    if(!loaded||incompatible||selected===null)return;
    const url=viewUrl(), requestEpoch=++shareEpoch;
    // Clipboard promises may settle after navigation, a filter change or a
    // second click. Neither success nor failure may resurrect an old link.
    const stillCurrent=()=>requestEpoch===shareEpoch&&loaded&&!incompatible&&selected!==null&&viewUrl()===url;
    try {
      if(!navigator.clipboard?.writeText)throw new Error('no clipboard');
      await navigator.clipboard.writeText(url);
      if(!stillCurrent())return;
      resetShareFallback();
      $('share-state').textContent='Exact dataset- and method-bound link copied.';
    } catch {
      if(!stillCurrent())return;
      const input=$('share-url');
      input.value=url;
      $('share-fallback').hidden=false;
      $('share-state').textContent='Clipboard unavailable. Select and copy the exact link below.';
      input.focus();
      input.select();
    }
  });
  $('clear').addEventListener('click',()=>{if(!loaded||incompatible)return;$('edition').value='all';$('subject').value='all';$('query').value='';renderCards();share(false);});
  $('retry').addEventListener('click',()=>{if(incompatible){
    // Retain the original path for Pages subdirectories and clear all stale
    // version/filter parameters; an absolute URL also works in offline readers.
    const reset=new URL(location.href);reset.search='';reset.hash='discover';
    history.replaceState({},'',reset.toString());restore();
  }else load();});
  window.addEventListener('popstate',()=>{if(loaded)restore();});
  load();
})();
