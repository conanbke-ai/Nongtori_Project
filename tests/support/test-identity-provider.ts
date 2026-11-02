export type TestIdentityRole = 'ADMIN' | 'OWNER' | 'WORKER';

export type FixedTestIdentity = Readonly<{
  subject: string;
  farmId: string;
  role: TestIdentityRole;
  displayName: string;
}>;

export const FIXED_TEST_IDENTITIES = Object.freeze({
  'admin-a': Object.freeze({
    subject: 'admin-a', farmId: 'farm-a', role: 'ADMIN', displayName: 'fixture admin a',
  }),
  'owner-a': Object.freeze({
    subject: 'owner-a', farmId: 'farm-a', role: 'OWNER', displayName: 'fixture owner a',
  }),
  'worker-a': Object.freeze({
    subject: 'worker-a', farmId: 'farm-a', role: 'WORKER', displayName: 'fixture worker a',
  }),
  'owner-b': Object.freeze({
    subject: 'owner-b', farmId: 'farm-b', role: 'OWNER', displayName: 'fixture owner b',
  }),
} satisfies Record<string, FixedTestIdentity>);

export type TestIdentitySubject = keyof typeof FIXED_TEST_IDENTITIES;

const identityHeaderPrefix = 'oai-authenticated-user-';

/**
 * Test-only adapter for direct handler calls. It does not grant a role itself:
 * production authorization still resolves the selected subject against the
 * in-memory farm_members fixture.
 */
export class TestIdentityProvider {
  readonly origin: string;

  constructor(origin = 'https://nongtori.test') {
    const parsed = new URL(origin);
    if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
      throw new Error('test identity provider origin must not include a path, query, or hash');
    }
    this.origin = parsed.origin;
  }

  identity(subject: TestIdentitySubject): FixedTestIdentity {
    return FIXED_TEST_IDENTITIES[subject];
  }

  requestAs(
    subject: TestIdentitySubject | null,
    pathname: string,
    init: RequestInit = {},
  ) {
    if (!pathname.startsWith('/') || pathname.startsWith('//')) {
      throw new Error('test identity requests require an origin-relative pathname');
    }
    return this.authenticate(subject, new Request(new URL(pathname, this.origin), init));
  }

  authenticate(subject: TestIdentitySubject | null, request: Request) {
    const headers = new Headers(request.headers);
    for (const name of [...headers.keys()]) {
      if (name.startsWith(identityHeaderPrefix)) headers.delete(name);
    }
    if (subject) {
      const identity = this.identity(subject);
      headers.set('oai-authenticated-user-id', identity.subject);
      headers.set('oai-authenticated-user-full-name', identity.displayName);
    }
    return new Request(request, { headers });
  }
}

export const testIdentityProvider = new TestIdentityProvider();
