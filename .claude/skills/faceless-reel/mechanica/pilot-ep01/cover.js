const {chromium}=require('playwright'),fs=require('fs'),path=require('path');
const P=JSON.parse(fs.readFileSync('/home/user/joestilllives.github.io/.claude/skills/faceless-reel/palette.json')).worlds.navy;
const hero='data:image/png;base64,'+fs.readFileSync(path.join(__dirname,'hero_full/f_0060.png')).toString('base64');
const html=`<html><body style="margin:0;width:1080px;height:1350px;background:${P.bg};font-family:Inter;color:${P.ink};overflow:hidden">
<div style="position:absolute;left:88px;top:110px;font:700 26px Inter;letter-spacing:5px;color:${P.accent}">HOW THINGS WORK &middot; 01</div>
<div style="position:absolute;left:88px;top:160px;width:900px;font:800 104px/1.0 'Inter Display',Inter;letter-spacing:-3px">How a key actually opens a lock</div>
<img src="${hero}" style="position:absolute;left:110px;top:400px;width:860px;height:860px">
<div style="position:absolute;left:88px;top:1250px;font:600 30px Inter;color:${P.muted}">Sourced from Yale&rsquo;s 1865 patent</div></body></html>`;
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1350}});await p.setContent(html);await p.waitForTimeout(300);await p.screenshot({path:path.join(__dirname,'cover_4x5.png')});await b.close();})();
