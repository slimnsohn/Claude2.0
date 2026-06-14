'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nautilus', {
  search: (query) => ipcRenderer.invoke('search', query),
  launch: (item) => ipcRenderer.invoke('launch', item),
  getHome: () => ipcRenderer.invoke('getHome'),
  getConfig: () => ipcRenderer.invoke('getConfig'),
  saveConfig: (config) => ipcRenderer.invoke('saveConfig', config),
  searchIndex: (query) => ipcRenderer.invoke('searchIndex', query),
  hide: () => ipcRenderer.send('window:hide'),
  onShown: (cb) => ipcRenderer.on('window:shown', cb),
});
