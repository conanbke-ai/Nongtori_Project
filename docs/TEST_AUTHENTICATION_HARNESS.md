# Test Authentication Harness

## Purpose

The test authentication harness supplies fixed identities to direct route-handler tests without adding a runtime authentication bypass. It exists only under `tests/` and keeps the production authorization path intact: application code still resolves the supplied identity subject through `farm_members` and applies the normal farm, role, ownership, and permission checks.

The harness is for isolated contract and workflow tests. It is not a replacement for testing real login, logout, session expiry, Sites identity-header provenance, or deployed hosting behavior.

## Fixed identities

| Fixture key | Identity subject | Farm fixture | Role fixture |
| --- | --- | --- | --- |
| `admin-a` | `admin-a` | `farm-a` | `ADMIN` |
| `owner-a` | `owner-a` | `farm-a` | `OWNER` |
| `worker-a` | `worker-a` | `farm-a` | `WORKER` |
| `owner-b` | `owner-b` | `farm-b` | `OWNER` |

Farm and role values seed the isolated in-memory membership table. They are never sent as request headers and do not grant authority by themselves. The production handler reads the fixed identity subject and obtains the effective farm and role from the fixture database through the same application authorization code used by normal requests.

## Usage

```ts
import { testIdentityProvider } from './support/test-identity-provider';

const ownerRequest = testIdentityProvider.requestAs(
  'owner-a',
  '/api/farmer-dashboard',
);

const anonymousRequest = testIdentityProvider.requestAs(
  null,
  '/api/farmer-dashboard',
);

const loopbackWorkerRequest = testIdentityProvider.authenticate(
  'worker-a',
  new Request('http://localhost/api/farmer-dashboard'),
);
```

Select an identity explicitly for every request. Use `null` for anonymous cases. Service-token routes continue to receive their normal fixture token through `globalThis.nongtoriTestEnv`; the identity provider does not synthesize service capabilities.

Run the harness and the authorization contract suite together:

```bash
pnpm test:auth-harness
```

## Safety boundary

- The provider is imported directly by tests; it is not registered in `tests/register.mjs`, an application route, middleware, or runtime environment.
- It accepts only an origin-relative fixture path when constructing a request. Query parameters and request hostnames never select an identity.
- It removes caller-supplied `oai-authenticated-user-*` headers before applying the selected fixed subject, so a test cannot accidentally retain a different caller identity.
- It sends no farm, role, permission, or administrator header.
- There is no production flag, environment variable, secret, global mutable current role, or localhost fallback that activates the provider.
- A regression test scans `app/**/*.ts` and `app/**/*.tsx` and fails if production sources reference the provider or its fixed identities. It also verifies that the test loader does not inject an identity automatically.
- Cross-farm access, insufficient roles, anonymous access, normal membership, and service-token decisions remain assertions against production handlers and the isolated D1/FILES fixtures.

## Deliberately separate verification

The harness does not expose a browser proxy, query switch, header control, or runtime role picker. A live browser role switch would need a separately designed trusted test boundary; none is enabled here. Real login/logout, session expiry, identity-header authenticity at the hosting edge, production D1/R2, and deployed-host behavior remain `NOT_RUN` and require their own acceptance environment.
