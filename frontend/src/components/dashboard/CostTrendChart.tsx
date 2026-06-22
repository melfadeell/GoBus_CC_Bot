import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyAnalyticsPoint } from '@/api/client'

interface CostTrendChartProps {
  data: DailyAnalyticsPoint[]
  height?: number
}

/** Estimated USD spend per day. */
export default function CostTrendChart({ data, height = 224 }: CostTrendChartProps) {
  const formatted = data.map((d) => ({ ...d, label: d.date.slice(5) }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={formatted} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="costFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#16a34a" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#16a34a" stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid var(--color-border-default)' }}
          formatter={(value) => [`$${Number(value ?? 0).toFixed(4)}`, 'Cost']}
          labelFormatter={(label) => `Date: ${label}`}
        />
        <Area
          type="monotone"
          dataKey="cost_usd"
          stroke="#16a34a"
          fill="url(#costFill)"
          strokeWidth={2}
          animationDuration={700}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
