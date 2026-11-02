export const dashboardScreens = [
  'home',
  'alerts',
  'history',
  'capture',
  'guide',
  'management',
  'account',
] as const;

export type DashboardScreen = typeof dashboardScreens[number];

type DashboardHistory = {
  pushState(data: unknown, unused: string, url?: string | URL | null): void;
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
};

export function dashboardScreenFromSearch(search: string): DashboardScreen | null {
  const value = new URLSearchParams(search).get('screen');
  return dashboardScreens.includes(value as DashboardScreen)
    ? value as DashboardScreen
    : null;
}

export function writeDashboardScreen({
  currentScreen,
  nextScreen,
  href,
  history,
  mode = 'push',
}: {
  currentScreen: DashboardScreen;
  nextScreen: DashboardScreen;
  href: string;
  history: DashboardHistory;
  mode?: 'push' | 'replace';
}): boolean {
  if (mode === 'push' && currentScreen === nextScreen) return false;

  const url = new URL(href);
  url.searchParams.set('screen', nextScreen);
  if (mode === 'replace') history.replaceState(null, '', url);
  else history.pushState(null, '', url);
  return true;
}
