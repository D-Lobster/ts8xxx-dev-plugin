const fs=require('fs'),path=require('path');
function scan(root){
const app=path.join(root,'APP');if(!fs.statSync(app).isDirectory())throw Error('APP is not a directory');
const files=[],findings=[],functions=[];
function walk(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){const f=path.join(d,e.name);if(e.isSymbolicLink())continue;if(e.isDirectory())walk(f);else if(/\.[ch]$/i.test(e.name))files.push(f);}}walk(app);
if(!files.length)throw Error('no C/H files under APP');
const controls=new Set(['if','for','while','switch','sizeof','return','_Static_assert']);
for(const f of files){
const raw=fs.readFileSync(f,'utf8'),rel=path.relative(root,f).replace(/\\/g,'/'),lines=raw.split(/\r?\n/);
const report=(rule,line,detail)=>findings.push({rule,file:rel,line,detail,status:'REVIEW_REQUIRED'});
const mask=x=>x.replace(/[^\r\n]/g,' ');
const code=raw.replace(/\/\*[\s\S]*?\*\/|\/\/[^\r\n]*|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'/g,mask);
const lineAt=i=>code.slice(0,i).split('\n').length;
lines.forEach((l,i)=>{if(l.length>100)report('R10',i+1,'line exceeds 100 characters');if(/^\s*\t/.test(l))report('R09',i+1,'tab in indentation');});
for(const m of code.matchAll(/\b(malloc|calloc|realloc|free)\s*\(/g))report('R16',lineAt(m.index),'allocation API candidate: '+m[1]);
for(const m of code.matchAll(/\b(?:\w*delay_ms|HAL_Delay)\s*\(/gi))report('R15',lineAt(m.index),'blocking delay candidate');
for(const m of raw.matchAll(/\b(?:TS_LOG_\w+|LOG_\w+|printf)\s*\(\s*"((?:\\.|[^"\\])*)"/g))if(/[^\x20-\x7e]/.test(m[1]))report('R26',lineAt(m.index),'non-ASCII log literal candidate');
let depth=0,start=0;
for(let i=0;i<code.length;i++){
const c=code[i];
if(c==='{'){
if(depth===0){const header=code.slice(start,i),m=header.match(/\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*$/);if(m&&!controls.has(m[1])){
let d=1,k=i+1;for(;k<code.length&&d;k++){if(code[k]==='{')d++;if(code[k]==='}')d--;}
if(d){report('R24',lineAt(i),'unbalanced candidate body');break;}
const body=code.slice(i+1,k-1),name=m[1],first=lineAt(start+m.index),last=lineAt(k-1);
const count=code.slice(start+m.index,k).split(/\r?\n/).filter(x=>x.trim()).length;
const calls=[...new Set([...body.matchAll(/\b([A-Za-z_]\w*)\s*\(/g)].map(x=>x[1]).filter(n=>!controls.has(n)))];
functions.push({name,file:rel,line:first,end_line:last,code_lines:count,calls});
if(count>50)report('R24',first,'function '+name+' has '+count+' code lines; review dispatch exception');
if(code.slice(0,i).split('\n').pop().trim())report('R08',lineAt(i),'function opening brace not on separate line');
i=k-1;start=k;continue;
}}
depth++;
}else if(c==='}') {depth=Math.max(0,depth-1);if(!depth)start=i+1;}else if(c===';'&&!depth)start=i+1;
}
}
const byName=new Map();for(const f of functions){const a=byName.get(f.name)||[];a.push(f);byName.set(f.name,a);}
let longest=[],cycles=[],ambiguous=[];const memo=new Map();
function chain(f,stack=[]){if(stack.includes(f)){cycles.push([...stack,f].map(x=>x.name));return [];}if(stack.length>128){cycles.push(['depth cap reached']);return [];}if(memo.has(f))return memo.get(f);let best=[f];for(const n of f.calls){const all=byName.get(n)||[];if(all.length>1){ambiguous.push(n);continue;}if(all.length===1){const tail=chain(all[0],[...stack,f]);if(tail.length+1>best.length)best=[f,...tail];}}memo.set(f,best);return best;}
for(const f of functions){const ch=chain(f);if(ch.length>longest.length)longest=ch;if(ch.length>3)findings.push({rule:'R24',file:f.file,line:f.line,detail:'direct call depth candidate '+ch.length,status:'REVIEW_REQUIRED'});}
return {schema_version:1,scope:'APP C/H; lexical candidates only',files:files.map(f=>path.relative(root,f)),functions,findings,metrics:{longest_function:functions.reduce((a,b)=>!a||b.code_lines>a.code_lines?b:a,null),direct_depth_candidate:longest.length,longest_direct_chain:longest.map(f=>({name:f.name,file:f.file,line:f.line})),cycles,ambiguous_names:[...new Set(ambiguous)]},limitations:['Not a C parser; macros, conditional compilation, function pointers, duplicate symbols, strings and complex declarations can affect coverage.','Code lines approximate; SDK and unresolved calls not counted. Direct graph depth is not a verified maximum.','No automatic PASS; manually verify all rules, including ISR context, naming and GPIO semantics.']};
}
if(require.main===module){try{if(!process.argv[2]||!process.argv[3])throw Error('Usage: node audit-app.cjs PROJECT_ROOT OUTPUT_JSON');const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);const result=scan(root);fs.mkdirSync(path.dirname(out),{recursive:true});fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n');console.log('scanned '+result.files.length+' files; '+result.findings.length+' candidates; '+out);}catch(e){console.error(e.message);process.exitCode=1;}}
module.exports={scan};
