'use strict';

async function launchItem(item, { shell }) {
  try {
    switch (item.type) {
      case 'app':
      case 'folder': {
        const error = await shell.openPath(item.target);
        return error ? { ok: false, error } : { ok: true };
      }
      case 'site':
      case 'claude':
        await shell.openExternal(item.target);
        return { ok: true };
      default:
        return { ok: false, error: `Unknown item type: ${item.type}` };
    }
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

module.exports = { launchItem };
