export const farmRoles = ['ADMIN', 'OWNER', 'WORKER'] as const;

export type FarmRole = (typeof farmRoles)[number];

export type FarmPermissions = {
  viewRevenue: boolean;
  manageMembers: boolean;
  manageFarm: boolean;
  uploadMedia: boolean;
  reviewAlerts: boolean;
  viewHistory: boolean;
};

const permissions: Record<FarmRole, FarmPermissions> = {
  ADMIN: {
    viewRevenue: true,
    manageMembers: true,
    manageFarm: true,
    uploadMedia: true,
    reviewAlerts: true,
    viewHistory: true,
  },
  OWNER: {
    viewRevenue: true,
    manageMembers: true,
    manageFarm: false,
    uploadMedia: true,
    reviewAlerts: true,
    viewHistory: true,
  },
  WORKER: {
    viewRevenue: false,
    manageMembers: false,
    manageFarm: false,
    uploadMedia: true,
    reviewAlerts: true,
    viewHistory: true,
  },
};

export function normalizeFarmRole(value: unknown): FarmRole {
  return typeof value === 'string' && farmRoles.includes(value as FarmRole)
    ? value as FarmRole
    : 'WORKER';
}

export function permissionsForRole(role: FarmRole): FarmPermissions {
  return { ...permissions[role] };
}

export function roleLabel(role: FarmRole) {
  return role === 'ADMIN' ? '관리자' : role === 'OWNER' ? '사업주' : '작업자';
}

export function can(role: FarmRole, permission: keyof FarmPermissions) {
  return permissions[role][permission];
}
