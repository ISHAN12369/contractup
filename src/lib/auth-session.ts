let tokenSource: (() => Promise<string | null>) | null = null;
let epoch = 0;

export function configureAuth(source: (() => Promise<string | null>) | null): void {
  tokenSource = source;
  epoch += 1;
}

export function authEpoch(): number { return epoch; }

export async function authenticatedHeaders(initial?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initial);
  const token = tokenSource ? await tokenSource() : null;
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}
