import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyAnalyticsPoint } from '@/api/client'

interface TokenUsageChartProps {
  data: DailyAnalyticsPoint[]
  height?: number
}

export default function TokenUsageChart({ data, height = 224 }: TokenUsageChartProps) {
  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(5),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={formatted} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} width={40} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid var(--color-border-default)' }}
          formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Tokens']}
          labelFormatter={(label) => `Date: ${label}`}
        />
        <Bar
          dataKey="tokens"
          fill="var(--color-brand-accent)"
          radius={[4, 4, 0, 0]}
          animationDuration={800}
          animationBegin={0}
        >
          <LabelList dataKey="tokens" position="top" fontSize={9} fill="var(--color-text-muted)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
