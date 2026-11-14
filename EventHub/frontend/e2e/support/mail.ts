import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

/**
 * Emails sent by the outbox worker, read back from its log.
 *
 * The stack under test runs with DJANGO_DEBUG=1 and no SMTP credentials, so
 * Django's console email backend prints every message (full MIME source) to
 * the worker's stdout, separated by a line of 79 dashes. That is the real
 * delivery path — the request only queues a job, the worker renders and
 * "sends" it — so reading the log proves the email was produced, without a
 * test-only endpoint in the application.
 *
 * E2E_WORKER_CONTAINER names the worker container (`eventhub_worker` in the
 * default compose project, `ehqa_worker` in the isolated QA stack).
 */
const run = promisify(execFile);
const WORKER = process.env['E2E_WORKER_CONTAINER'] || 'eventhub_worker';
const SEPARATOR = /^-{79}$/m;

export interface Mail {
  to: string[];
  subject: string;
  /** The Date header (whole seconds). */
  date: Date;
  /** The text/plain body (decoded). */
  text: string;
  /** The text/html body (decoded), if any. */
  html: string;
  /** Content-IDs of inline parts (ticket QR codes). */
  inlineIds: string[];
}

function decodeWords(value: string): string {
  // RFC 2047 encoded words, as Django writes non-ASCII subjects.
  return value.replace(
    /=\?([^?]+)\?([QqBb])\?([^?]*)\?=\s*/g,
    (_m, _charset: string, kind: string, data: string) =>
      kind.toUpperCase() === 'B'
        ? Buffer.from(data, 'base64').toString('utf8')
        : Buffer.from(
            data
              .replace(/_/g, ' ')
              .replace(/=([0-9A-Fa-f]{2})/g, (_x, h: string) =>
                String.fromCharCode(parseInt(h, 16)),
              ),
            'latin1',
          ).toString('utf8'),
  );
}

function splitHead(raw: string): { headers: Map<string, string>; body: string } {
  const index = raw.search(/\r?\n\r?\n/);
  const head = index === -1 ? raw : raw.slice(0, index);
  const body = index === -1 ? '' : raw.slice(index).replace(/^\r?\n\r?\n/, '');
  const headers = new Map<string, string>();
  for (const line of head.replace(/\r?\n[ \t]+/g, ' ').split(/\r?\n/)) {
    const colon = line.indexOf(':');
    if (colon > 0)
      headers.set(line.slice(0, colon).trim().toLowerCase(), line.slice(colon + 1).trim());
  }
  return { headers, body };
}

function decodeBody(body: string, encoding = ''): string {
  switch (encoding.toLowerCase()) {
    case 'base64':
      return Buffer.from(body.replace(/\s+/g, ''), 'base64').toString('utf8');
    case 'quoted-printable':
      return Buffer.from(
        body
          .replace(/=\r?\n/g, '')
          .replace(/=([0-9A-Fa-f]{2})/g, (_x, h: string) => String.fromCharCode(parseInt(h, 16))),
        'latin1',
      ).toString('utf8');
    default:
      return body;
  }
}

function walk(raw: string, mail: Mail): void {
  const { headers, body } = splitHead(raw);
  const type = headers.get('content-type') ?? 'text/plain';
  const boundary = /boundary="?([^";]+)"?/i.exec(type)?.[1];
  if (type.toLowerCase().startsWith('multipart/') && boundary) {
    for (const part of body.split(`--${boundary}`).slice(1)) {
      if (part.startsWith('--')) break;
      walk(part.replace(/^\r?\n/, ''), mail);
    }
    return;
  }
  const contentId = headers.get('content-id');
  if (contentId) mail.inlineIds.push(contentId.replace(/[<>]/g, ''));
  const text = decodeBody(body, headers.get('content-transfer-encoding'));
  if (type.toLowerCase().startsWith('text/plain') && !mail.text) mail.text = text.trim();
  if (type.toLowerCase().startsWith('text/html') && !mail.html) mail.html = text;
}

export function parseMail(raw: string): Mail | null {
  const { headers } = splitHead(raw.trim());
  const to = headers.get('to');
  if (!to) return null;
  const mail: Mail = {
    to: to.split(',').map((a) => a.trim().toLowerCase()),
    subject: decodeWords(headers.get('subject') ?? ''),
    date: new Date(headers.get('date') ?? 0),
    text: '',
    html: '',
    inlineIds: [],
  };
  walk(raw.trim(), mail);
  return mail;
}

export async function workerMails(): Promise<Mail[]> {
  const { stdout } = await run('docker', ['logs', WORKER], { maxBuffer: 256 * 1024 * 1024 });
  return stdout
    .split(SEPARATOR)
    .map(parseMail)
    .filter((m): m is Mail => m !== null);
}

export interface MailQuery {
  /** Only emails sent at or after this moment (the Date header has whole seconds). */
  since?: Date;
  timeoutMs?: number;
}

function sentSince(mail: Mail, since?: Date): boolean {
  return !since || mail.date.getTime() >= Math.floor(since.getTime() / 1000) * 1000;
}

/**
 * The newest email to `to` that matches, polling the worker log until it
 * shows up (the worker picks jobs up every couple of seconds).
 */
export async function waitForMail(
  to: string,
  match: (mail: Mail) => boolean = () => true,
  { since, timeoutMs = 30_000 }: MailQuery = {},
): Promise<Mail> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const found = (await workerMails())
      .reverse()
      .find((m) => m.to.includes(to.toLowerCase()) && sentSince(m, since) && match(m));
    if (found) return found;
    if (Date.now() > deadline) throw new Error(`No email to ${to} matched within ${timeoutMs} ms`);
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

/** All emails to `to` that match (no waiting). */
export async function mailsTo(to: string, match: (mail: Mail) => boolean = () => true) {
  return (await workerMails()).filter((m) => m.to.includes(to.toLowerCase()) && match(m));
}

/** The 6-digit code of the newest matching email, e.g. a sign-up or 2FA code. */
export async function waitForCode(
  to: string,
  phrase: RegExp,
  query: MailQuery = {},
): Promise<string> {
  const mail = await waitForMail(to, (m) => phrase.test(m.text), query);
  const code = new RegExp(`${phrase.source}\\s*(\\d{6})`).exec(mail.text)?.[1];
  if (!code) throw new Error(`No code after ${phrase} in: ${mail.text}`);
  return code;
}
