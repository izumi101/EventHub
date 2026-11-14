import { createHmac } from 'node:crypto';

const STEP_MS = 30_000;

/** RFC 6238 code (SHA-1, 6 digits, 30 s) for a base32 secret. */
export function totp(secret: string, now = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const ch of secret.replace(/=+$/, '').replace(/\s+/g, '').toUpperCase()) {
    bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  }
  const key = Buffer.from(bits.match(/.{8}/g)?.map((b) => parseInt(b, 2)) ?? []);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(now / STEP_MS)));
  const mac = createHmac('sha1', key).update(counter).digest();
  const offset = mac[mac.length - 1] & 0xf;
  return ((mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, '0');
}

// The backend accepts each time step once per user (replay protection), so
// a second sign-in of the same account inside one 30 s window must wait for
// the next one. Remember the last step used per account in this process.
const lastStep = new Map<string, number>();

/** A code for `account` from a time step not used yet in this run. */
export async function freshTotp(account: string, secret: string): Promise<string> {
  const step = Math.floor(Date.now() / STEP_MS);
  const used = lastStep.get(account);
  if (used !== undefined && used >= step) {
    await new Promise((resolve) => setTimeout(resolve, (used + 1) * STEP_MS - Date.now() + 250));
  }
  const now = Date.now();
  lastStep.set(account, Math.floor(now / STEP_MS));
  return totp(secret, now);
}

/** Mark the current step used (after the server refused it as a replay). */
export function burnCurrentStep(account: string): void {
  lastStep.set(account, Math.floor(Date.now() / STEP_MS));
}
