/**
 * TS8XXX series development plugin for DeepSeek Harness.
 *
 * The plugin's content is a patch-layer bundle (`dsh.bundle.patch` ->
 * `cordis.patch.yml`): installing the bundle mounts the "TS8XXX 系列开发"
 * agent preset, which in turn assembles the TS800X workflow skills shipped
 * under `_hook_skills/`. Nothing needs to run at the Host plugin layer, so
 * `apply` is intentionally a no-op.
 *
 * It is exported because marketplace listings require a plugin entry that
 * exports `apply(ctx)`; bundle patch layers alone are not reflected through
 * the module graph.
 */

/** @param {unknown} _ctx DSH host context (unused: patch-layer bundle). */
export function apply(_ctx) {
  // No host rows: the preset and skills are mounted from cordis.patch.yml.
}

export default { apply }
