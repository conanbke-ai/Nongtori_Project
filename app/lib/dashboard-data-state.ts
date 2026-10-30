export type DashboardDataState = 'initial-loading' | 'initial-error' | 'ready' | 'refreshing' | 'stale';

export function dashboardDataState({
  hasSuccessfulData,
  loading,
  error,
}: {
  hasSuccessfulData: boolean;
  loading: boolean;
  error: string;
}): DashboardDataState {
  if (!hasSuccessfulData) return loading ? 'initial-loading' : 'initial-error';
  if (error) return 'stale';
  return loading ? 'refreshing' : 'ready';
}
