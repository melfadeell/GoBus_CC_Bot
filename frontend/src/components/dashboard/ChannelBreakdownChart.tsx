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
import type { ChannelTokenStat } from '@/api/client'

interface ChannelBreakdownChartProps {
  data: ChannelTokenStat[]
  channelLabel: (ch: string) => string
  height?: number
}

export default function ChannelBreakdownChart({
  data,
  channelLabel,
  height = 224,
}: ChannelBreakdownChartProps) {
  const formatted = data.map((d) => ({
    ...d,
    name: channelLabel(d.channel),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={formatted} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 10 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={72} />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: '1px solid var(--color-border-default)' }}
          formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Tokens']}
        />
        <Bar
          dataKey="total_tokens"
          fill="var(--color-brand-primary)"
          radius={[0, 4, 4, 0]}
          animationDuration={900}
        >
          <LabelList dataKey="total_tokens" position="right" fontSize={9} fill="var(--color-text-muted)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
