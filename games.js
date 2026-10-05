/* TonUp phase 2 UI. Loaded after index.html's script; reuses its globals (api, t, toast, fmt, esc, hap, U, lang, tg). */
(()=>{
const G={fa:{daily:'گردونه روزانه',dailyS:'چرخش رایگان روزانه',crash:'کرش',crashS:'قبل از ترکیدن موشک برداشت کن',arena:'آرنا',arenaS:'مبارزه با حریف',bomb:'بمب',bombS:'به بمب نخور',wheel:'گردونه تون‌آپ',wheelS:'ریسک و پاداش',play:'بازی کن',soon:'بازی‌ها به‌زودی می‌آیند',off:'غیرفعال',spin:'بچرخان',next:'چرخش بعدی',congrats:'🎉 تبریک!',stake:'مبلغ ورود',start:'شروع بازی',confirm:'تأیید و پرداخت',cash:'برداشت کن',crashed:'ترکید!',won:'بردی',lost:'باختی',draw:'مساوی (برگشت مبلغ)',bombs:'تعداد بمب',rules:'قوانین',rtp:'بازگشت به بازیکن',hist:'ضریب‌های اخیر',commit:'هش تضمین',seed:'سید (برای راستی‌آزمایی)',attack:'حمله',defend:'دفاع',charge:'شارژ',you:'تو',foe:'حریف سیستم',round:'راند',again:'دوباره',daily_r:'هر روز یک چرخش رایگان. نتیجه فقط توسط سرور تعیین می‌شود.',crash_r:'ضریب از 1.00x شروع می‌شود. قبل از ترکیدن برداشت کن، وگرنه مبلغ از دست می‌رود.',bomb_r:'خانه‌های امن ضریب را بالا می‌برند. هر زمان می‌توانی برداشت کنی. بمب یعنی باخت.',arena_r:'۳ راند. حمله از شارژ، شارژ از دفاع و دفاع از حمله برنده است. حریف سیستم است و حرکاتش از قبل با هش قفل شده. برد 1.9x.',wheel_r:'مبلغ 1 تا 10 TON. جدول احتمالات زیر دقیقاً همان است که سرور استفاده می‌کند.',e_bad_stake:'مبلغ مجاز نیست',e_insufficient:'موجودی کافی نیست',e_game_disabled:'این بازی فعلاً غیرفعال است',e_already_open:'یک بازی باز دارید',e_already_spun:'امروز چرخانده‌اید',very_low:'خیلی کم',low:'کم',medium:'متوسط',high:'زیاد',very_high:'خیلی زیاد'},
en:{daily:'Daily Wheel',dailyS:'FREE DAILY SPIN',crash:'Crash',crashS:'RIDE THE MULTIPLIER',arena:'Arena',arenaS:'BATTLE THE ARENA',bomb:'Bomb',bombS:"DON'T HIT THE BOMB",wheel:'TonUp Wheel',wheelS:'RISK & REWARD',play:'PLAY',soon:'Games are coming soon',off:'Disabled',spin:'SPIN',next:'Next free spin',congrats:'🎉 Congratulations',stake:'Entry',start:'START',confirm:'CONFIRM & PAY',cash:'CASH OUT',crashed:'Crashed!',won:'You won',lost:'You lost',draw:'Draw (stake refunded)',bombs:'Bombs',rules:'Rules',rtp:'Return to player',hist:'Recent multipliers',commit:'Fairness hash',seed:'Seed (verify)',attack:'Attack',defend:'Defend',charge:'Charge',you:'You',foe:'System opponent',round:'Round',again:'AGAIN',daily_r:'One free spin per day. The result is decided only by the server.',crash_r:'Multiplier starts at 1.00x. Cash out before it crashes or lose your entry.',bomb_r:'Safe tiles raise the multiplier. Cash out any time. A bomb ends the round.',arena_r:'3 rounds. Attack beats Charge, Charge beats Defend, Defend beats Attack. The opponent is the system and its moves are hash-committed up front. Win pays 1.9x.',wheel_r:'Entry 1 to 10 TON. The table below is exactly what the server uses.',e_bad_stake:'Amount not allowed',e_insufficient:'Insufficient balance',e_game_disabled:'This game is disabled',e_already_open:'You have an open game',e_already_spun:'Already spun today',very_low:'Very low',low:'Low',medium:'Medium',high:'High',very_high:'Very high'}};
const g=k=>G[lang][k]||k, $$=id=>document.getElementById(id);
const rid=()=>crypto.randomUUID?crypto.randomUUID():Math.random().toString(36).slice(2)+Date.now().toString(36);
let C=null,raf=0,poll=0,tick=0,cur=0;
const stop=()=>{cancelAnimationFrame(raf);clearInterval(poll);clearInterval(tick)};
// ---- sound + fx
let ac;const snd=()=>localStorage.snd!=='0';
function beep(f=600,d=.08,ty='sine'){if(!snd())return;try{ac=ac||new(window.AudioContext||webkitAudioContext)();const o=ac.createOscillator(),v=ac.createGain();o.type=ty;o.frequency.value=f;v.gain.value=.05;o.connect(v);v.connect(ac.destination);o.start();v.gain.exponentialRampToValueAtTime(.0001,ac.currentTime+d);o.stop(ac.currentTime+d)}catch{}}
const sfx={click:()=>beep(520,.05),spin:()=>beep(300,.3,'triangle'),win:()=>{beep(660,.1);setTimeout(()=>beep(880,.18),110)},lose:()=>beep(160,.3,'sawtooth'),boom:()=>beep(90,.45,'square')};
function confetti(){for(let i=0;i<26;i++){const e=document.createElement('i');e.textContent=['🪙','✨','🎉'][i%3];e.style.cssText='position:fixed;top:40%;left:50%;z-index:40;font-style:normal;pointer-events:none;transition:transform 1.2s cubic-bezier(.22,1,.36,1),opacity 1.2s';document.body.appendChild(e);requestAnimationFrame(()=>{e.style.transform=`translate(${(Math.random()-.5)*320}px,${(Math.random()-.4)*320}px) rotate(${Math.random()*360}deg)`;e.style.opacity=0});setTimeout(()=>e.remove(),1300)}}
// ---- style
document.head.insertAdjacentHTML('beforeend',`<style>
#gm{position:fixed;inset:0;background:radial-gradient(120% 50% at 50% 0,oklch(0.28 0.12 285),var(--bg0) 60%);z-index:8;display:none;flex-direction:column;max-width:480px;margin:0 auto}
#gm.on{display:flex;animation:in .4s var(--ease)}.gh{display:flex;justify-content:space-between;align-items:center;padding:calc(12px + env(safe-area-inset-top)) 16px 8px}
.gb{flex:1;overflow:auto;padding:8px 16px calc(24px + env(safe-area-inset-bottom))}
.gc{border-radius:26px;padding:20px;margin-bottom:12px;border:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:transform .3s var(--ease);position:relative;overflow:hidden}.gc:active{transform:scale(.97)}
.gc em{font-size:50px;font-style:normal;animation:fl 3.5s ease-in-out infinite}.gc.off{opacity:.45;pointer-events:none}.gc h3{font-size:18px}.gc .go{display:inline-block;margin-top:8px;background:oklch(1 0 0/.18);border-radius:12px;padding:5px 16px;font-size:12px;font-weight:800}
.wp{text-align:center;font-size:26px;color:var(--gold);margin-bottom:-14px;position:relative;z-index:2}
.wh{width:270px;height:270px;border-radius:50%;margin:0 auto;position:relative;border:5px solid oklch(1 0 0/.15);box-shadow:0 0 50px oklch(0.6 0.22 290/.6)}
.wh span{position:absolute;top:50%;left:50%;font-weight:800;font-size:12px;transform-origin:0 0;text-shadow:0 1px 3px #0008;white-space:nowrap}
.wc{position:absolute;inset:50% auto auto 50%;width:54px;height:54px;margin:-27px;border-radius:50%;background:var(--bg0);display:grid;place-items:center;font-size:26px;border:3px solid var(--gold)}
.sb{display:flex;gap:8px;align-items:center;margin:14px 0}.sb input[type=number]{flex:1;background:var(--bg0);border:1px solid var(--line);border-radius:14px;padding:11px;color:var(--text);font:inherit;text-align:center;font-size:18px}
.sb button{flex:0 0 auto}.q{background:var(--bg2);border:1px solid var(--line);color:var(--text);border-radius:12px;padding:8px 12px;font:inherit;font-size:12px}.q.on{border-color:var(--cyan);color:var(--cyan)}
.rl{font-size:12px;color:var(--mut);line-height:1.7;margin:8px 0}.bn{text-align:center;padding:16px;border-radius:22px;margin:12px 0;font-weight:800;font-size:20px;animation:in .4s var(--ease)}
.bn.w{background:oklch(0.5 0.17 150/.3);border:1px solid oklch(0.8 0.17 150)}.bn.l{background:oklch(0.5 0.2 20/.3);border:1px solid oklch(0.7 0.2 20)}.bn.d{background:var(--bg2);border:1px solid var(--line)}
.cm{font-size:64px;font-weight:800;text-align:center;font-family:'Chakra Petch',sans-serif;margin:6px 0}.cm.x{color:oklch(0.7 0.2 20)}
.cw{position:relative;height:170px;background:var(--bg1);border-radius:22px;border:1px solid var(--line);overflow:hidden}.cw svg{width:100%;height:100%}
#rk{position:absolute;font-size:30px;transform:translate(-50%,-50%);transition:none}
.hs{display:flex;gap:6px;overflow:auto;margin:10px 0}.hs b{flex:0 0 auto;padding:4px 10px;border-radius:10px;background:var(--bg2);font-size:12px;font-family:'Chakra Petch',sans-serif}.hs b.g{color:var(--cyan)}
.bg{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}.bg button{aspect-ratio:1;border-radius:16px;border:1px solid var(--line);background:linear-gradient(160deg,var(--bg2),var(--bg1));font-size:26px;color:var(--text);cursor:pointer;transition:transform .2s var(--ease)}
.bg button:active{transform:scale(.9)}.bg button.s{background:oklch(0.45 0.14 190/.5);border-color:var(--cyan)}.bg button.m{background:oklch(0.4 0.14 25/.4)}.bg button.h{animation:bx .5s var(--ease);background:oklch(0.5 0.22 25/.6)}@keyframes bx{30%{transform:scale(1.25) rotate(8deg)}60%{transform:scale(.9) rotate(-8deg)}}
.ar{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;text-align:center;margin:10px 0}.ar .pc{background:var(--bg1);border:1px solid var(--line);border-radius:22px;padding:14px 6px}.ar .pc em{font-size:34px;font-style:normal;display:block}
.ab{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.ab button{border-radius:18px;border:1px solid var(--line);background:var(--bg2);color:var(--text);padding:14px 4px;font:inherit;font-weight:800;cursor:pointer}.ab button:active{transform:scale(.94)}.ab button span{display:block;font-size:26px}
.tb{width:100%;border-collapse:collapse;font-size:13px}.tb td{padding:5px 2px;border-bottom:1px solid var(--line)}.tb td:last-child{text-align:end;color:var(--mut)}
.fz{font-size:10px;color:var(--mut);word-break:break-all;margin-top:8px;direction:ltr;text-align:left}
</style>`);
// ---- helpers
const gerr=e=>{const c=e&&typeof e.code==='object'?e.code.code:e&&e.code;toast(e&&e.status===503?t('maint'):G[lang]['e_'+c]||t('err'));hap('error')};
const btn=(id,txt,cls='')=>`<button class="btn ${cls}" id="${id}">${txt}</button>`;
function twoStep(b,label,fn){b.onclick=()=>{if(b.dataset.c){b.dataset.c='';fn();return}b.dataset.c=1;b.dataset.o=b.textContent;b.textContent=label();sfx.click();tg?.HapticFeedback?.impactOccurred('light');setTimeout(()=>{if(b.dataset.c){b.dataset.c='';b.textContent=b.dataset.o}},3500)}}
function stakeBox(game,def){const c=C.games[game];return `<div class="sb"><button class="q" data-d="-">−</button><input type="number" id="sk" inputmode="decimal" min="${c.min}" max="${c.max}" step="any" value="${def??c.min}"><button class="q" data-d="+">+</button></div><div class="sb" style="margin-top:-6px">${[c.min,1,5,c.max].filter((v,i,a)=>a.indexOf(v)===i).map(v=>`<button class="q" data-v="${v}">${v}</button>`).join('')}</div>`}
function bindStake(){document.querySelectorAll('.sb .q').forEach(q=>q.onclick=()=>{const i=$$('sk');if(q.dataset.v)i.value=q.dataset.v;else i.value=Math.max(+i.min,Math.min(+i.max,+(+i.value+(q.dataset.d==='+'?1:-1)*(+i.max>5?1:.1)).toFixed(2)));i.dispatchEvent(new Event('input'))})}
const stake=()=>parseFloat($$('sk').value)||0;
function overlay(title,body){let o=$$('gm');if(!o){o=document.createElement('div');o.id='gm';document.body.appendChild(o)}
o.innerHTML=`<div class="gh"><button class="chip" id="gx">${lang==='fa'?'→':'←'}</button><b>${title}</b><button class="chip" id="gsn">${snd()?'🔊':'🔇'}</button></div><div class="gb" id="gbd">${body}</div>`;o.classList.add('on');
$$('gx').onclick=closeG;$$('gsn').onclick=()=>{localStorage.snd=snd()?'0':'1';$$('gsn').textContent=snd()?'🔊':'🔇'};tg?.BackButton?.show();tg?.BackButton?.onClick(closeG)}
function closeG(){stop();$$('gm')?.classList.remove('on');tg?.BackButton?.hide();tg?.BackButton?.offClick(closeG);refresh()}
async function refresh(){try{U=await api('/me');renderProfile();renderPlay()}catch{}}
function banner(res,txt){const c=res==='win'?'w':res==='draw'?'d':'l';if(res==='win'){sfx.win();confetti();hap('success')}else if(res==='lose'){sfx.lose();hap('error')}return `<div class="bn ${c}">${txt}</div>`}
function fair(v){return `<div class="fz">${g('commit')}: ${v.commit}${v.seed?`<br>${g('seed')}: ${v.seed}`:''}</div>`}
// ---- wheel widget
const COLS=['oklch(0.55 0.22 300)','oklch(0.5 0.2 250)','oklch(0.6 0.15 215)','oklch(0.5 0.22 340)','oklch(0.6 0.15 85)'];
function wheelHTML(labels){const n=labels.length,sg=360/n;cur=0;return `<div class="wp">▼</div><div class="wh" id="wh" style="background:conic-gradient(${labels.map((_,i)=>`${COLS[i%5]} ${i*sg}deg ${(i+1)*sg}deg`).join(',')})">${labels.map((l,i)=>`<span style="transform:rotate(${(i+.5)*sg}deg) translateY(-98px) translate(-50%,-50%)">${l}</span>`).join('')}<div class="wc">🪙</div></div>`}
function spinTo(idx,n,cb){const el=$$('wh'),sg=360/n;cur=cur-(cur%360)+360*6+(360-(idx+.5)*sg);el.style.transition='transform 4.5s cubic-bezier(.1,.7,.1,1)';el.style.transform=`rotate(${cur}deg)`;sfx.spin();tg?.HapticFeedback?.impactOccurred('medium');setTimeout(cb,4600)}
// ---- game center
async function renderPlay(){let ok=false;try{C=await api('/games/config');ok=true}catch{}
const el=$$('play');if(!ok||!Object.values(C.games).some(x=>x.on)){el.innerHTML=`<div class="empty"><em>🎮</em><h3>${g('soon')}</h3></div>`;return}
const L=[['daily','🎡','linear-gradient(135deg,oklch(0.5 0.2 300),oklch(0.4 0.18 250))'],['crash','🚀','linear-gradient(135deg,oklch(0.45 0.16 230),oklch(0.25 0.06 260))'],['arena','⚔️','linear-gradient(135deg,oklch(0.5 0.2 20),oklch(0.26 0.08 300))'],['bomb','💣','linear-gradient(135deg,oklch(0.45 0.14 150),oklch(0.24 0.05 200))'],['wheel','💎','linear-gradient(135deg,oklch(0.6 0.15 85),oklch(0.3 0.08 50))']];
el.innerHTML=L.map(([k,e,bg])=>`<div class="gc ${C.games[k].on?'':'off'}" data-g="${k}" style="background:${bg}"><div><h3>${g(k)}</h3><p class="mut" style="color:oklch(1 0 0/.75)">${g(k+'S')}</p><span class="go">${C.games[k].on?(k==='daily'&&!C.daily.available?'⏳':g('play')):g('off')}</span></div><em>${e}</em></div>`).join('');
el.querySelectorAll('.gc').forEach(c=>c.onclick=()=>{sfx.click();tg?.HapticFeedback?.impactOccurred('light');open_[c.dataset.g]()})}
const open_={daily,crash,arena,bomb,wheel};
const resume=(game)=>C.open.find(o=>o.game===game);
// ---- daily
function daily(){const P=C.daily.prizes,labels=P.map(p=>'+'+p.amount);
overlay(g('daily'),`<p class="rl">${g('daily_r')}</p>${wheelHTML(labels)}<div id="dr" style="margin-top:18px"></div>${btn('ds',g('spin'))}<p class="mut c" id="cd" style="margin-top:10px;text-align:center"></p>
<div class="card" style="margin-top:14px">${P.map(p=>`<div class="li" style="border:0;padding:6px 0"><span>${g(p.tier)}</span><span class="t en">+${p.amount} TON</span></div>`).join('')}</div>`);
const b=$$('ds');const cd=()=>{const ms=C.daily.next_ms-(Date.now()-(Date.now()-C.server_ms)-0)+0,r=C.daily.next_ms-Date.now();const s=Math.max(0,Math.floor(r/1000)),f=n=>String(n).padStart(2,'0');$$('cd').textContent=`${g('next')}: ${f(s/3600|0)}:${f(s/60%60|0)}:${f(s%60)}`};
const lock=()=>{b.disabled=true;cd();tick=setInterval(cd,1000)};if(!C.daily.available)lock();
b.onclick=async()=>{b.disabled=true;try{const r=await api('/games/daily/spin',{method:'POST'});spinTo(r.idx,P.length,()=>{$$('dr').innerHTML=banner('win',`${g('congrats')}<br>+${r.amount} TON`);C.daily.available=false;U.balance=r.balance;lock()})}catch(e){gerr(e);b.disabled=false}}}
// ---- TonUp wheel
function wheel(){const W=C.wheel;overlay(g('wheel'),`<p class="rl">${g('wheel_r')}</p><div id="wv"></div>${stakeBox('wheel',1)}<div id="tbl"></div>${btn('ws',g('spin'),'v')}<div id="wr"></div>`);bindStake();
const draw=()=>{const s=stake(),T=s>=W.split?W.wheel_high:W.wheel_low;$$('wv').innerHTML=wheelHTML(T.rows.map(r=>'x'+r.mult));
$$('tbl').innerHTML=`<div class="card"><table class="tb">${T.rows.map(r=>`<tr><td class="en">x${r.mult} → ${(s*r.mult).toFixed(2)} TON</td><td>${(r.p*100).toFixed(1)}%</td></tr>`).join('')}<tr><td>${g('rtp')}</td><td>${(T.rtp*100).toFixed(1)}%</td></tr></table></div>`};
let last=0;const chk=()=>{const k=stake()>=W.split?1:0;if(k!==last||!$$('wh')){last=k;draw()}else draw()};draw();$$('sk').oninput=()=>{const n=stake()>=W.split?1:0;if(n!==last){last=n;draw()}else{const T=n?W.wheel_high:W.wheel_low,s=stake();$$('tbl').innerHTML=`<div class="card"><table class="tb">${T.rows.map(r=>`<tr><td class="en">x${r.mult} → ${(s*r.mult).toFixed(2)} TON</td><td>${(r.p*100).toFixed(1)}%</td></tr>`).join('')}<tr><td>${g('rtp')}</td><td>${(T.rtp*100).toFixed(1)}%</td></tr></table></div>`}};
const b=$$('ws'),id=rid();twoStep(b,()=>`${g('confirm')} ${stake()} TON`,async()=>{b.disabled=true;try{const r=await api('/games/wheel/play',{method:'POST',body:JSON.stringify({stake:stake(),request_id:id})});const T=stake()>=W.split?W.wheel_high:W.wheel_low;spinTo(r.idx,T.rows.length,()=>{U.balance=r.balance;$$('wr').innerHTML=banner(r.mult>=1?'win':'lose',`x${r.mult} → ${r.payout} TON`)+fair(r);b.disabled=false;b.textContent=g('again');twoStep(b,()=>g('confirm'),()=>wheel())})}catch(e){gerr(e);b.disabled=false}})}
// ---- crash
async function crash(){overlay(g('crash'),`<p class="rl">${g('crash_r')}</p><div class="cm en" id="cm">1.00x</div><div class="cw"><svg viewBox="0 0 300 170" preserveAspectRatio="none"><polyline id="pl" fill="none" stroke="oklch(0.82 0.14 215)" stroke-width="3" stroke-linecap="round"/></svg><div id="rk">🚀</div></div><div id="cr"></div><div id="cc">${stakeBox('crash',0.1)}${btn('cs',g('start'))}</div><p class="rl" style="margin-top:14px">${g('hist')}</p><div class="hs" id="hs"></div>`);bindStake();hist();
const show=v=>{stop();const open=v.status==='open';if(open){run(v)}else end(v)};
const b=$$('cs'),id=rid();twoStep(b,()=>`${g('confirm')} ${stake()} TON`,async()=>{try{show(await api('/games/crash/start',{method:'POST',body:JSON.stringify({stake:stake(),request_id:id})}))}catch(e){gerr(e);if(e.code&&e.code.session_id)show(await api('/games/session/'+e.code.session_id))}});
const r=resume('crash');if(r)show(await api('/games/session/'+r.id));
async function hist(){try{const h=await api('/games/crash/history');$$('hs').innerHTML=h.map(x=>`<b class="${x>=2?'g':''}">${x.toFixed(2)}x</b>`).join('')}catch{}}
function run(v){$$('cc').innerHTML=btn('cx',g('cash')+' • '+v.stake+' TON','');$$('cr').innerHTML='';const off=Date.now()-v.server_ms,t0=v.t0_ms+off;let done=false;
$$('cx').onclick=async()=>{if(done)return;done=true;$$('cx').disabled=true;try{const r=await api('/games/crash/cashout',{method:'POST',body:JSON.stringify({session_id:v.id})});stop();end(r)}catch(e){gerr(e);done=false}};
const draw=()=>{const el=(Date.now()-t0)/1000,m=Math.floor(100*Math.exp(v.growth*el))/100;$$('cm').textContent=m.toFixed(2)+'x';$$('cx')&&($$('cx').textContent=`${g('cash')} • ${(v.stake*m).toFixed(3)} TON`);
const mt=Math.max(8,el*1.15),mm=Math.max(2,m*1.15),pts=[];for(let i=0;i<=40;i++){const tt=el*i/40;pts.push(`${(tt/mt*290+5).toFixed(1)},${(160-Math.log(Math.exp(v.growth*tt))/Math.log(mm)*150).toFixed(1)}`)}
$$('pl').setAttribute('points',pts.join(' '));const l=pts[40].split(',');$$('rk').style.left=(l[0]/300*100)+'%';$$('rk').style.top=(l[1]/170*100)+'%';raf=requestAnimationFrame(draw)};draw();
poll=setInterval(async()=>{try{const s=await api('/games/session/'+v.id);if(s.status==='resolved'){stop();end(s)}}catch{}},500)}
function end(v){stop();const win=v.result==='win';$$('cm').textContent=(win?v.cash:v.crash).toFixed(2)+'x';$$('cm').classList.toggle('x',!win);if(!win){sfx.boom();$$('rk').textContent='💥'}
$$('cr').innerHTML=banner(win?'win':'lose',win?`${g('won')} ${v.payout} TON`:`${g('crashed')} ${v.crash.toFixed(2)}x`)+fair(v);U.balance=v.balance;
$$('cc').innerHTML=btn('ca',g('again'));$$('ca').onclick=()=>crash();hist()}}
// ---- bomb
async function bomb(){let n=3;overlay(g('bomb'),`<p class="rl">${g('bomb_r')}</p><div id="bi"></div><div class="bg" id="bgrid"></div><div id="br"></div><div id="bc">${stakeBox('bomb',0.1)}<p class="rl">${g('bombs')}</p><div class="sb">${[1,3,5,10].map(x=>`<button class="q ${x===3?'on':''}" data-n="${x}">${x} 💣</button>`).join('')}</div>${btn('bs',g('start'))}</div>`);bindStake();
const grid=$$('bgrid');grid.innerHTML=Array.from({length:25},(_,i)=>`<button data-c="${i}" disabled>?</button>`).join('');
document.querySelectorAll('[data-n]').forEach(q=>q.onclick=()=>{n=+q.dataset.n;document.querySelectorAll('[data-n]').forEach(x=>x.classList.toggle('on',x===q))});
const id=rid(),b=$$('bs');twoStep(b,()=>`${g('confirm')} ${stake()} TON`,async()=>{try{paint(await api('/games/bomb/start',{method:'POST',body:JSON.stringify({stake:stake(),bombs:n,request_id:id})}))}catch(e){gerr(e);if(e.code&&e.code.session_id)paint(await api('/games/session/'+e.code.session_id))}});
const r=resume('bomb');if(r)paint(await api('/games/session/'+r.id));
function paint(v,hit){const open=v.status==='open';const cells=grid.children;
for(let i=0;i<25;i++){const c=cells[i];c.className='';c.disabled=!open;c.textContent='?';if(v.picked.includes(i)){c.className='s';c.textContent='💎'}if(!open&&v.mines?.includes(i)){c.className='m';c.textContent='💣'}if(hit===i){c.className='h';c.textContent='💥'}}
$$('bi').innerHTML=`<div class="cm en" style="font-size:44px">${v.mult.toFixed(2)}x</div>`;U.balance=v.balance;
if(open){$$('bc').innerHTML=btn('bx',`${g('cash')} • ${v.cashout.toFixed(3)} TON`)+(v.next?`<p class="mut" style="text-align:center;margin-top:6px">→ ${v.next.toFixed(2)}x</p>`:'');$$('bx').disabled=!v.picked.length;
$$('bx').onclick=async()=>{try{const r=await api('/games/bomb/cashout',{method:'POST',body:JSON.stringify({session_id:v.id})});paint(r)}catch(e){gerr(e)}};
[...cells].forEach(c=>c.onclick=async()=>{try{sfx.click();tg?.HapticFeedback?.impactOccurred('light');const r=await api('/games/bomb/pick',{method:'POST',body:JSON.stringify({session_id:v.id,cell:+c.dataset.c})});if(r.result==='lose'){sfx.boom();tg?.HapticFeedback?.notificationOccurred('error')}paint(r,r.hit)}catch(e){gerr(e)}})}
else{$$('br').innerHTML=banner(v.result,v.result==='win'?`${g('won')} ${v.payout} TON`:g('lost'))+fair(v);$$('bc').innerHTML=btn('ba',g('again'));$$('ba').onclick=()=>bomb()}}}
// ---- arena
async function arena(){const I={attack:'⚔️',defend:'🛡',charge:'⚡'};overlay(g('arena'),`<p class="rl">${g('arena_r')}</p><div class="ar"><div class="pc"><em>🧑‍🚀</em>${g('you')}</div><b class="en" id="sc">0 : 0</b><div class="pc"><em>🤖</em>${g('foe')}</div></div><div id="ar"></div><div id="ac">${stakeBox('arena',0.5)}${btn('as',g('start'))}</div><div id="am"></div>`);bindStake();
const id=rid(),b=$$('as');twoStep(b,()=>`${g('confirm')} ${stake()} TON`,async()=>{try{paint(await api('/games/arena/start',{method:'POST',body:JSON.stringify({stake:stake(),request_id:id})}))}catch(e){gerr(e);if(e.code&&e.code.session_id)paint(await api('/games/session/'+e.code.session_id))}});
const r=resume('arena');if(r)paint(await api('/games/session/'+r.id));
function paint(v){U.balance=v.balance;const me=v.rounds.filter(x=>x.res==='win').length,op=v.rounds.filter(x=>x.res==='lose').length;$$('sc').textContent=me+' : '+op;
$$('ar').innerHTML=v.rounds.map((x,i)=>`<div class="card" style="padding:10px;display:flex;justify-content:space-between;align-items:center"><span>${g('round')} ${i+1}</span><span style="font-size:26px">${I[x.me]} vs ${I[x.opp]}</span><b>${x.res==='win'?'✅':x.res==='lose'?'❌':'➖'}</b></div>`).join('');
if(v.status==='open'){$$('ac').innerHTML=`<div class="ab">${['attack','defend','charge'].map(a=>`<button data-a="${a}"><span>${I[a]}</span>${g(a)}</button>`).join('')}</div>`;
document.querySelectorAll('[data-a]').forEach(x=>x.onclick=async()=>{sfx.click();tg?.HapticFeedback?.impactOccurred('medium');try{paint(await api('/games/arena/move',{method:'POST',body:JSON.stringify({session_id:v.id,action:x.dataset.a})}))}catch(e){gerr(e)}})}
else{$$('ac').innerHTML=btn('aa',g('again'));$$('aa').onclick=()=>arena();$$('am').innerHTML=banner(v.result,v.result==='win'?`${g('won')} ${v.payout} TON`:v.result==='draw'?g('draw'):g('lost'))+fair(v)}}}
// ---- hooks into the base app
const _al=applyLang;applyLang=function(){_al();if(token&&$$('play').classList.contains('on'))renderPlay()};
const _ld=load;load=function(s){_ld(s);if(s==='play')renderPlay()};
})();
