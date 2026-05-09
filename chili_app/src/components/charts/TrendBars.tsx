import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type Datum = {
  label: string
  value: number
}

type TrendBarsProps = {
  color: string
  data: Datum[]
}

export function TrendBars({ color, data }: TrendBarsProps) {
  return (
    <ResponsiveContainer height="100%" width="100%">
      <BarChart data={data} margin={{ top: 8, right: 0, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="rgba(37, 52, 80, 0.6)" strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="label" stroke="#8899bb" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
        <YAxis stroke="#8899bb" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} width={34} />
        <Tooltip
          cursor={{ fill: 'rgba(0, 212, 255, 0.06)' }}
          contentStyle={{
            background: '#101828',
            border: '1px solid #253450',
            borderRadius: '9px',
            color: '#e2eaf6',
          }}
        />
        <Bar dataKey="value" fill={color} radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}