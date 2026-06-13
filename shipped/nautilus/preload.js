'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nautilus', {
  search: (query) => ipcRenderer.invoke('search', query),
  launch: (item) => ipcRenderer.invoke('launch', item),
  hide: () => ipcRenderer.send('window:hide'),
  onShown: (cb) => ipcRenderer.on('window:shown', cb),
});
