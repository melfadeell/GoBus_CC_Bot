import {
  Area,
  AreaChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyAnalyticsPoint } from '@/api/client'

interface MessagesTrendChartProps {
  data: DailyAnalyticsPoint[]
  height?: number
}

export default function MessagesTrendChart({ data, height = 224 }: MessagesTrendChartProps) {
  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(5),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={formatted} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="msgGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-brand-primary)" stopOpacity={0.35} />
            <stop offset="95%" stopColor="var(--color-brand-primary)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} width={32} allowDecimals={false} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid var(--color-border-default)' }}
          formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Messages']}
        />
        <Area
          type="monotone"
          dataKey="messages"
          stroke="var(--color-brand-primary)"
          fill="url(#msgGradient)"
          strokeWidth={2}
          animationDuration={800}
          dot={{ r: 2, fill: 'var(--color-brand-primary)' }}
          activeDot={{ r: 5 }}
        >
          <LabelList dataKey="messages" position="top" fontSize={9} fill="var(--color-text-muted)" />
        </Area>
      </AreaChart>
    </ResponsiveContainer>
  )
}
