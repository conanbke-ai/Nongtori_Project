export type DashboardDataState = 'initial-loading' | 'initial-error' | 'ready' | 'refreshing' | 'stale';

export function dashboardSelection({ farmId, itemIds, currentItemId }: {
  farmId: string; itemIds: readonly string[]; currentItemId: string;
}): { farmId: string; itemId: string } {
  if (!farmId) return { farmId: '', itemId: '' };
  return { farmId, itemId: itemIds.includes(currentItemId) ? currentItemId : itemIds[0] ?? '' };
}

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
