"use client";

import { Line, LineChart, ResponsiveContainer } from "recharts";

export function Sparkline({ data, colorVar }: { data: number[]; colorVar: string }) {
  if (data.length < 2) {
    return null;
  }
  const points = data.map((value, index) => ({ index, value }));

  return (
    <div className="h-10 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={`var(${colorVar})`}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
