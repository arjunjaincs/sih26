const { contextBridge } = require('electron');

/**
 * PRAMAAN v1 Secure Desktop Preload
 * Context isolation: true
 * Node integration: false
 * Exposes only safe, immutable workstation metadata.
 */
contextBridge.exposeInMainWorld('pramaanDesktop', {
  isDesktop: true,
  environment: 'development',
  platform: process.platform,
  version: '1.0.0'
});
