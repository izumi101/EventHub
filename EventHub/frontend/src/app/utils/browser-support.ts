/**
 * Feature detection for browser APIs that the DOM typings declare as always
 * present, although many browsers (or insecure contexts) do not provide them.
 * Checking with `in` keeps the test honest at runtime without fighting the types.
 */

/** Web Share API: mostly mobile browsers; missing on most desktop ones. */
export function supportsWebShare(): boolean {
  return 'share' in navigator;
}

/** Whether these files can go through the Web Share API. */
export function canShareFiles(files: File[]): boolean {
  return 'canShare' in navigator && navigator.canShare({ files });
}

/** Camera access: `navigator.mediaDevices` only exists in secure contexts. */
export function supportsCamera(): boolean {
  return 'mediaDevices' in navigator && 'getUserMedia' in navigator.mediaDevices;
}
