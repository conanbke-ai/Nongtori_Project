export type ServiceTokenDecision = 'AUTHORIZED' | 'UNCONFIGURED' | 'DENIED';

/**
 * Service credentials are the only worker/vendor trust boundary. Request URL,
 * hostname, and forwarding headers never grant service access.
 */
export function serviceTokenDecision(
  request: Request,
  configuredToken: string | undefined,
): ServiceTokenDecision {
  if (!configuredToken) return 'UNCONFIGURED';
  return request.headers.get('authorization') === `Bearer ${configuredToken}`
    ? 'AUTHORIZED'
    : 'DENIED';
}
