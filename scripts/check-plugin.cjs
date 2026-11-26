const fs=require('fs'),p=require('path');
const root=p.resolve(__dirname,'..'),read=f=>fs.readFileSync(p.join(root,f),'utf8').replace(/^\uFEFF/,'').replace(/\r\n/g,'\n').trimEnd();
const mirror='_hook_skills/ts800x-coding-standard/SKILL.md',standard=read('RULES/CODING_STANDARD.md');
const begin='<!-- BEGIN GENERATED STANDARD -->',end='<!-- END GENERATED STANDARD -->';
let s=read(mirror),i=s.indexOf(begin),j=s.indexOf(end);
if(i<0||j<i)throw Error('generated markers missing');
const expected=s.slice(0,i)+begin+'\n'+standard+'\n'+s.slice(j);
if(process.argv.includes('--sync')){fs.writeFileSync(p.join(root,mirror),expected+'\n');s=expected;}
const errors=[];
if(s!==expected)errors.push('coding standard mirror drift');
for(let i=1;i<=29;i++){const id='R'+String(i).padStart(2,'0');if(!standard.includes('| '+id+' |'))errors.push('missing rule '+id);if(!read('RULES/REVIEW_CHECKLIST.md').includes('- [ ] '+id+' '))errors.push('missing checklist '+id);}
const m=JSON.parse(read('workflow.manifest.json')),pkg=JSON.parse(read('package.json'));
for(const sk of m.skills){const f=p.join(root,sk.source,'SKILL.md');if(!fs.existsSync(f))errors.push('missing skill '+sk.name);else if(!fs.readFileSync(f,'utf8').includes('name: '+sk.name))errors.push('skill name mismatch '+sk.name);}
for(const [k,v] of Object.entries(m.hooks||{}))for(const n of v)if(!m.skills.some(s=>s.name===n))errors.push('unknown hook '+k+': '+n);
for(const v of Object.values(m.policies||{}))if(!fs.existsSync(p.join(root,v)))errors.push('missing policy '+v);
if(pkg.version!==read('VERSION')||pkg.version!==m.workflow_version)errors.push('version mismatch');
for(const f of pkg.files)if(!fs.existsSync(p.join(root,f)))errors.push('missing package entry '+f);
if(errors.length){console.error(errors.join('\n'));process.exitCode=1;}else console.log('PASS: exact mirror, R01-R29 checklist, skill registration, policies, package entries and version');
