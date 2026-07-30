import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import Card from "./Card";
import MockBadge from "./MockBadge";

export const chartColor = "#E8A33D";
export const gridColor = "#232A35";

export default function BarWidget({ title, data, xKey, yKey, height = 220 }) {
  return (
    <Card title={title} action={<MockBadge />}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ left: 10 }}>
          <CartesianGrid stroke={gridColor} horizontal={false} />
          <XAxis type="number" stroke="#8992A3" fontSize={11} />
          <YAxis type="category" dataKey={xKey} stroke="#8992A3" fontSize={11} width={150} />
          <Tooltip contentStyle={{ background: "#171C24", border: "1px solid #232A35", fontSize: 12 }} />
          <Bar dataKey={yKey} fill={chartColor} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
