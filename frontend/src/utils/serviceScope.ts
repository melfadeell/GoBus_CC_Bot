export const SERVICE_CODES = ['gobus', 'gomini', 'golemo'] as const

export function parseServiceScope(scope: string): { all: boolean; services: string[] } {
  if (!scope || scope === 'all') return { all: true, services: [] }
  return { all: false, services: scope.split(',').map((s) => s.trim()).filter(Boolean) }
}

export function serializeServiceScope(all: boolean, services: string[]): string {
  if (all) return 'all'
  return services.join(',') || 'gobus'
}
