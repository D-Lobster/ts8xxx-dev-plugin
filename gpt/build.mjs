import { execFileSync } from 'node:child_process';
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const adapter = dirname(fileURLToPath(import.meta.url));
const root = dirname(adapter);
const read = path => readFileSync(join(root, path), 'utf8');
const write = (path, contents) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents, { flag: 'wx' });
};
const writeJson = (path, object) => write(path, JSON.stringify(object, null, 2) + '\n');

const manifest = JSON.parse(read('gpt/plugin.json'));
const workflow = JSON.parse(read('workflow.manifest.json'));
const version = read('VERSION').trim();
if (manifest.version !== version ||
    workflow.workflow_version !== version ||
    JSON.parse(read('package.json')).version !== version) {
  throw new Error('Sync the GPT manifest version with DSH and the workflow before packaging.');
}
const names = new Set(workflow.skills.map(skill => skill.name));
if (workflow.skills.length !== 24 || names.size !== workflow.skills.length) {
  throw new Error('Expected 24 unique DSH skills. Review the inventory before changing it.');
}
execFileSync(process.execPath, [join(root, 'scripts/check-plugin.cjs')], { cwd: root, stdio: 'inherit' });

const marketplace = resolve(process.argv[2] ?? join(root, 'dist/gpt-marketplace'));
const pluginPath = join(marketplace, 'plugins', manifest.name);
mkdirSync(pluginPath, { recursive: true });
writeJson(join(pluginPath, 'plugin.json'), manifest);
cpSync(join(adapter, 'remote-app.json'), join(pluginPath, '.app.json'), {
  force: false, errorOnExist: true,
});

const safety = read('gpt/windows-safety.md').trim();
for (const { name, source } of workflow.skills) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name) || source !== `_hook_skills/${name}`) {
    throw new Error(`Invalid canonical skill path for ${name}`);
  }
  const original = read(`${source}/SKILL.md`);
  const sections = original.match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n)([\s\S]*)$/);
  if (!sections || !sections[1].split(/\r?\n/).includes(`name: ${name}`)) {
    throw new Error(`Invalid canonical frontmatter for ${name}`);
  }
  const destination = join(pluginPath, 'skills', name);
  write(join(destination, 'SKILL.md'), sections[1] +
    `\n${safety}\n\nDSH 版本 ${version}。流程与规则快照位于 ts800x-workflow 的 references/。\n\n` +
    sections[2]);
  // Only ship tracked reference documents, with the original relative paths.
  const references = execFileSync('git', ['ls-files', '-z', '--', `${source}/references/`],
    { cwd: root, encoding: 'utf8' }).split('\0').filter(path => path.endsWith('.md'));
  for (const path of references) {
    write(join(destination, path.slice(source.length + 1)), read(path));
  }
}
const workflowReferences = join(pluginPath, 'skills', 'ts800x-workflow', 'references');
for (const path of [
  'VERSION', 'LICENSE', 'AGENTS.md', 'GPT_REMOTE.md', 'WORKFLOW.md', 'workflow.manifest.json',
  'RULES/CODING_STANDARD.md', 'RULES/REVIEW_CHECKLIST.md', 'RULES/CODING_STYLE_GAP_ANALYSIS.md',
  'TEMPLATES/MEMORY_TEMPLATE.md', 'TEMPLATES/PROGRESS_TEMPLATE.md', 'TEMPLATES/TODO_TEMPLATE.md',
]) {
  write(join(workflowReferences, path), read(path));
}

writeJson(join(marketplace, '.agents/plugins/marketplace.json'), {
  name: 'ts8xxx-local',
  interface: { displayName: 'TS8XXX 个人插件' },
  plugins: [{
    name: manifest.name,
    source: { source: 'local', path: `./plugins/${manifest.name}` },
    policy: { installation: 'AVAILABLE', authentication: 'ON_INSTALL' },
    category: manifest.extensions['com.openai'].interface.category,
  }],
});
console.log(pluginPath);
