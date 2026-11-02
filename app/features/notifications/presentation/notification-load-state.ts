export function notificationLoadState({ loading, failed, loaded, rowCount }: {
  loading: boolean; failed: boolean; loaded: boolean; rowCount: number;
}) {
  if (loading || (!loaded && !failed)) return 'LOADING';
  if (failed) return rowCount > 0 ? 'STALE' : 'ERROR';
  return rowCount > 0 ? 'READY' : 'EMPTY';
}
