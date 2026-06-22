import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyAnalyticsPoint } from '@/api/client'

interface TokenSplitChartProps {
  data: DailyAnalyticsPoint[]
  height?: number
  inputLabel?: string
  outputLabel?: string
}

/** Stacked bar of input (prompt) vs output (completion) tokens per day. */
export default function TokenSplitChart({
  data,
  height = 224,
  inputLabel = 'Input',
  outputLabel = 'Output',
}: TokenSplitChartProps) {
  const formatted = data.map((d) => ({ ...d, label: d.date.slice(5) }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={formatted} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} width={40} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid var(--color-border-default)' }}
          formatter={(value, name) => [Number(value ?? 0).toLocaleString(), name]}
          labelFormatter={(label) => `Date: ${label}`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar
          dataKey="prompt_tokens"
          name={inputLabel}
          stackId="t"
          fill="var(--color-brand-primary)"
          radius={[0, 0, 0, 0]}
          animationDuration={700}
        />
        <Bar
          dataKey="completion_tokens"
          name={outputLabel}
          stackId="t"
          fill="var(--color-brand-accent)"
          radius={[4, 4, 0, 0]}
          animationDuration={700}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
