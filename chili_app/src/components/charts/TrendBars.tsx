import { useEffect, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts'

type Datum = {
  label: string
  value: number
}

type TrendBarsProps = {
  color: string
  data: Datum[]
}

export function TrendBars({ color, data }: TrendBarsProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const node = containerRef.current
    if (!node) {
      return
    }

    const updateSize = () => {
      const nextWidth = node.clientWidth
      const nextHeight = node.clientHeight
      setSize((current) => {
        if (current.width === nextWidth && current.height === nextHeight) {
          return current
        }
        return { width: nextWidth, height: nextHeight }
      })
    }

    updateSize()

    const observer = new ResizeObserver(() => {
      updateSize()
    })
    observer.observe(node)

    return () => {
      observer.disconnect()
    }
  }, [])

  return (
    <div className="chart-shell" ref={containerRef}>
      {size.width > 0 && size.height > 0 ? (
        <BarChart data={data} height={size.height} margin={{ top: 8, right: 0, left: -18, bottom: 0 }} width={size.width}>
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
      ) : null}
    </div>
  )
}