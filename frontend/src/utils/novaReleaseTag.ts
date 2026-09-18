/** Renderer copy of VERSION (vNNN). Vite injects this for web and Electron. */
export function novaRendererReleaseTag(): string {
  return typeof __NOVA_RELEASE_TAG__ === 'string' ? __NOVA_RELEASE_TAG__.trim() : '';
}
