"""Read-only dashboard for the local bridge.

The page contains GET-only browser code. Mutations remain available only through
the existing approval APIs and are intentionally not linked from this view.
"""

from __future__ import annotations

DASHBOARD_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ChatGPT Cursor Bridge · Developer Console</title>
<style>
:root{color-scheme:dark;--bg:#08111f;--panel:#101d30;--panel2:#14263b;--line:#28415b;--text:#e8f1fb;--muted:#91a8bf;--cyan:#5eead4;--blue:#60a5fa;--amber:#fbbf24;--red:#fb7185}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#163a54 0,transparent 34%),linear-gradient(145deg,var(--bg),#0d1726 56%,#101b2d);font:14px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;color:var(--text)}main{max-width:1280px;margin:auto;padding:36px 22px 60px}.eyebrow{color:var(--cyan);font-size:11px;font-weight:800;letter-spacing:.2em;text-transform:uppercase}.hero{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:30px}.hero h1{font-size:clamp(30px,5vw,56px);line-height:1.02;margin:10px 0 12px;letter-spacing:-.05em}.hero p{color:var(--muted);max-width:640px;margin:0}.pulse{border:1px solid #2b5564;background:#102d36;color:var(--cyan);border-radius:999px;padding:8px 12px;white-space:nowrap}.grid{display:grid;gap:16px;grid-template-columns:repeat(12,1fr)}.card{background:linear-gradient(145deg,rgba(20,38,59,.92),rgba(13,27,45,.96));border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 16px 40px #0003}.span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-5{grid-column:span 5}.span-7{grid-column:span 7}.span-8{grid-column:span 8}.span-12{grid-column:span 12}.card h2{font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);margin:0 0 16px}.metric{font-size:30px;font-weight:800;letter-spacing:-.04em}.sub{color:var(--muted);font-size:12px}.status{display:inline-flex;gap:7px;align-items:center}.dot{width:8px;height:8px;border-radius:50%;background:var(--cyan);box-shadow:0 0 14px var(--cyan)}.dot.bad{background:var(--red);box-shadow:0 0 14px var(--red)}.dot.warn{background:var(--amber);box-shadow:0 0 14px var(--amber)}.list{display:grid;gap:9px}.row{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid #ffffff0d;padding-bottom:8px}.row:last-child{border:0}.tag{border-radius:6px;padding:2px 7px;background:#1f3854;color:#bcd4ea;font-size:11px}.timeline{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}.stage{min-height:88px;padding:9px;border:1px solid var(--line);border-radius:11px;background:#0d1b2d}.stage strong{display:block;font-size:10px;letter-spacing:.08em}.stage small{display:block;color:var(--muted);margin-top:10px;font-size:10px}.stage.done{border-color:#287d76;background:#103338}.stage.active{border-color:var(--blue);box-shadow:inset 0 -3px var(--blue)}.stage.wait{border-color:var(--amber)}pre{max-height:230px;overflow:auto;white-space:pre-wrap;background:#07101c;border:1px solid #ffffff12;border-radius:10px;padding:12px;color:#b7d0e6;font-size:11px;margin:0}.empty{color:var(--muted);font-style:italic}.footer{margin-top:22px;color:var(--muted);font-size:11px;text-align:right}@media(max-width:900px){.span-3,.span-4,.span-5,.span-7,.span-8{grid-column:span 12}.timeline{grid-template-columns:repeat(2,1fr)}.hero{display:block}.pulse{display:inline-block;margin-top:18px}}
</style>
</head>
<body><main>
<div class="hero"><div><div class="eyebrow">Phase 7 · Developer Experience</div><h1>Developer Console</h1><p>Read-only visibility into projects, workflows, approvals, memory and audit activity. Changes still require the existing Preview → Approval → Execution flow.</p></div><div class="pulse" id="refresh">Loading…</div></div>
<section class="grid">
<div class="card span-3"><h2>System health</h2><div id="health" class="empty">Loading…</div></div>
<div class="card span-3"><h2>Projects</h2><div id="projects" class="metric">—</div><div class="sub">workspace projects</div></div>
<div class="card span-3"><h2>Workflows</h2><div id="workflows" class="metric">—</div><div class="sub">persisted pipelines</div></div>
<div class="card span-3"><h2>Approvals</h2><div id="approvals" class="metric">—</div><div class="sub">pending decisions</div></div>
<div class="card span-7"><h2>Workflow activity</h2><div id="workflow-list" class="list empty">Loading…</div></div>
<div class="card span-5"><h2>Memory</h2><div id="memory-list" class="list empty">Loading…</div></div>
<div class="card span-12"><h2>Audit stream</h2><div id="audit" class="list empty">Loading…</div></div>
</section><div class="footer">Auto-refreshes every 10 seconds · read-only dashboard</div>
</main>
<script>
const $=id=>document.getElementById(id);const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function get(path){const r=await fetch(path,{headers:{accept:'application/json'}});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function health(data){const checks=Object.entries(data.checks||{});$('health').innerHTML='<div class="status"><i class="dot '+(data.status==='ok'?'':'bad')+'"></i><b>'+esc(data.status.toUpperCase())+'</b></div><div class="sub" style="margin-top:9px">'+checks.map(([k,v])=>esc(k)+': '+esc(v.status)).join(' · ')+'</div>'}
function list(id,items,empty,render){$(id).innerHTML=items.length?items.map(render).join(''): '<span class="empty">'+empty+'</span>'}
async function refresh(){try{const [h,p,w,a,m]=await Promise.all([get('/system/health'),get('/workspace/list'),get('/workflow/list'),get('/permission/pending'),get('/memory/list')]);health(h);$('projects').textContent=p.projects.length;$('workflows').textContent=w.workflows.length;$('approvals').textContent=a.pending.length;list('workflow-list',w.workflows,'No workflows yet',x=>'<div class="row"><span><b>'+esc(x.name)+'</b><br><span class="sub">'+esc(x.project)+' · '+esc(x.currentStage)+'</span></span><span class="tag">'+esc(x.status)+'</span></div>');list('memory-list',m.projects,'No memory initialized',x=>'<div class="row"><span>'+esc(x.project)+'</span><span class="tag">'+x.documents.length+' docs</span></div>');const audit=await get('/audit/log?limit=12');list('audit',audit.entries,'No audit entries yet',x=>'<div class="row"><span><b>'+esc(x.action)+'</b><br><span class="sub">'+esc(x.path)+'</span></span><span class="tag">'+esc(x.result)+'</span></div>');$('refresh').textContent='Updated '+new Date().toLocaleTimeString()}catch(error){$('health').innerHTML='<div class="status"><i class="dot bad"></i><b>UNAVAILABLE</b></div><div class="sub">'+esc(error.message)+'</div>';$('refresh').textContent='Refresh failed'}}
refresh();setInterval(refresh,10000);
</script></body></html>'''
