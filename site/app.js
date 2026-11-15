'use strict';
const $ = id => document.getElementById(id);
const number = n => Number(n).toLocaleString();
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL = text => {try {const u=new URL(text); return ['http:','https:'].includes(u.protocol) ? escapeHTML(u.href) : '#';} catch {return '#';}};
const date = text => text ? new Date(text).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}) : 'Date unavailable';
let data, preferences = {};
try {preferences=JSON.parse(localStorage.getItem('3dsrp-reading') || '{}');} catch {}
function store(){try {localStorage.setItem('3dsrp-reading',JSON.stringify(preferences));} catch {}}
function metrics(){
 const history=data.history||[], latest=history.at(-1), prior=history.at(-2);
 const delta=key => !prior ? 'Daily history starts with this snapshot' : `${latest[key]-prior[key]>=0?'+':''}${number(latest[key]-prior[key])} since ${date(prior.date)}`;
 const views=(data.traffic?.views||[]).filter(d => Date.now()-Date.parse(d.timestamp)<14*86400000);
 const cards=[['Release downloads',latest?.downloads,latest?delta('downloads'):'Awaiting GitHub collection'],['GitHub stars',latest?.stars,latest?delta('stars'):'Awaiting GitHub collection'],['Repository views · 14 days',views.length?views.reduce((s,x)=>s+x.count,0):null,views.length?'Visits, including repeat visitors':'Repository traffic access not configured'],['Discovered mentions',Object.keys(data.mentions).length,'Partial coverage · see source status']];
 $('metrics').innerHTML=cards.map(([label,value,note])=>`<div class="metric"><span class="label">${label}</span><strong>${value==null?'—':number(value)}</strong><small>${escapeHTML(note)}</small></div>`).join('');
}
function chart(){
 const h=data.history||[], key=$('trend-metric').value;
 if(h.length<2){$('chart').innerHTML='<div class="empty">Your history starts here. A trend will appear after the next daily snapshot.</div>';return;}
 const values=h.map(x=>x[key]), min=Math.min(...values), max=Math.max(...values), span=max-min||1;
 const start=Date.parse(h[0].date), duration=Date.parse(h.at(-1).date)-start||1;
 const points=h.map(x=>`${10+(Date.parse(x.date)-start)/duration*980},${140-(x[key]-min)/span*120}`).join(' ');
 $('chart').innerHTML=`<svg viewBox="0 0 1000 160" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(key)} changed from ${values[0]} to ${values.at(-1)}"><line x1="10" y1="140" x2="990" y2="140" stroke="#30383c"/><polyline points="${points}" fill="none" stroke="#b7f275" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><div class="chart-labels"><span>${date(h[0].date)} · ${number(values[0])}</span><span>${date(h.at(-1).date)} · ${number(values.at(-1))}</span></div>`;
}
function mentions(){
 const q=$('search').value.toLowerCase(), platform=$('platform').value, reading=$('reading').value;
 const entries=Object.entries(data.mentions).filter(([id,m])=>{
  const p=preferences[id]||{};
  return (!platform||m.platform===platform)&&`${m.title} ${m.author||''} ${m.community||''}`.toLowerCase().includes(q)&&(reading==='hidden'?p.hidden:!p.hidden)&&(reading!=='saved'||p.saved)&&(reading!=='unread'||!p.read);
 }).sort((a,b)=>Date.parse(b[1].published_at||b[1].first_seen)-Date.parse(a[1].published_at||a[1].first_seen));
 $('mention-count').textContent=`(${entries.length})`;
 $('mentions').innerHTML=entries.map(([id,m])=>{
  const p=preferences[id]||{}, stats=Object.entries(m.metrics||{}).map(([k,v])=>`${number(v)} ${escapeHTML(k)}`).join(' · ')||'Metrics unavailable';
  const change=m.comment_change>0?` · +${number(m.comment_change)} comments since previous check`:'';
  return `<article class="mention" data-id="${escapeHTML(id)}"><div class="mention-top"><span class="tag">${escapeHTML(m.platform)}</span><span>${m.published_at?date(m.published_at):'Added '+date(m.first_seen)}</span></div><h3><a class="post-link" href="${safeURL(m.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(m.title)} ↗</a></h3><div class="byline">${escapeHTML([m.author,m.community].filter(Boolean).join(' · ')||m.discovery)}${m.author==='stepcach'?' · Project announcement':''}</div><div class="mention-bottom"><span class="engagement">${stats}${change}</span><div class="actions"><button data-action="read" aria-pressed="${!!p.read}">${p.read?'Read':'Mark read'}</button><button data-action="saved" aria-pressed="${!!p.saved}">${p.saved?'Saved':'Save'}</button><button data-action="hidden">${p.hidden?'Restore':'Hide'}</button></div></div>${m.updated_at?`<div class="fine">Checked ${date(m.updated_at)}</div>`:''}</article>`;
 }).join('')||'<p class="empty-feed">No mentions match these filters.</p>';
}
function searches(){
 const q=$('query').value, enc=encodeURIComponent;
 const links=[['Reddit',`https://www.reddit.com/search/?q=${enc(q)}&sort=new`],['YouTube',`https://www.youtube.com/results?search_query=${enc(q)}`],['X',`https://x.com/search?q=${enc(q)}&f=live`],['Facebook',`https://www.facebook.com/search/posts/?q=${enc(q)}`],['Instagram (web)',`https://www.google.com/search?q=${enc('site:instagram.com '+q)}`],['Web',`https://www.google.com/search?q=${enc(q)}`]];
 $('search-links').innerHTML=links.map(([label,url])=>`<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`).join('');
}
async function init(){
 try{
  const response=await fetch('data/dashboard.json',{cache:'no-store'}); if(!response.ok)throw new Error('No snapshot'); data=await response.json();
  const stale=Date.now()-Date.parse(data.generated_at)>36*3600000;
  $('freshness').textContent=`${stale?'⚠ Snapshot overdue · ':''}Updated ${new Date(data.generated_at).toLocaleString()}`; $('freshness').classList.toggle('stale',stale);
  metrics();chart();mentions();
  $('sources').innerHTML=Object.entries(data.sources).map(([name,s])=>`<div class="source"><strong><span class="dot ${escapeHTML(s.status)}"></span>${escapeHTML(name)} · ${s.status==='ok'?'Connected':s.status==='setup'?'Setup needed':'Refresh failed'}</strong><p>${escapeHTML(s.message)}</p>${s.last_success?`<p>Last success: ${date(s.last_success)}</p>`:''}</div>`).join('');
  $('query').innerHTML=data.queries.map(q=>`<option>${escapeHTML(q)}</option>`).join(''); searches();
  $('assets').innerHTML=(data.assets||[]).map(a=>`<tr><td><a href="${safeURL(a.url)}">${escapeHTML(a.name)} ↗</a></td><td>${escapeHTML(a.release)}</td><td>${escapeHTML(a.group)}</td><td class="number">${number(a.downloads)}</td></tr>`).join('');
 }catch{ $('error').hidden=false;$('error').textContent='Could not load the dashboard snapshot. Refresh the page or check the collection workflow.';$('freshness').textContent='Snapshot unavailable';}
}
for(const id of ['search','platform','reading'])$(id).addEventListener('input',()=>data&&mentions());
$('trend-metric').addEventListener('change',()=>data&&chart());$('query').addEventListener('change',searches);
$('mentions').addEventListener('click',event=>{
 const article=event.target.closest('[data-id]');if(!article)return;
 const button=event.target.closest('button'), link=event.target.closest('.post-link');if(!button&&!link)return;
 const id=article.dataset.id,p=preferences[id]||{};
 if(button)p[button.dataset.action]=!p[button.dataset.action];else p.read=true;
 preferences[id]=p;store();if(button)mentions();
});
init();
