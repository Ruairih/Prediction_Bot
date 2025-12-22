/**
 * Equity Curve Chart Component
 */
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { EquityPoint } from '../../types';

export interface EquityCurveChartProps {
  data: EquityPoint[];
}

export function EquityCurveChart({ data }: EquityCurveChartProps) {
  const formatDate = (timestamp: string) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const formatValue = (value: number) => `$${value.toFixed(0)}`;

  return (
    <div
      data-testid="equity-curve-chart"
      className="bg-bg-secondary rounded-lg p-4 border border-border"
    >
      <h3 className="text-lg font-semibold mb-4 text-text-primary">Equity Curve</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatDate}
              stroke="#8b949e"
              fontSize={12}
            />
            <YAxis
              tickFormatter={formatValue}
              stroke="#8b949e"
              fontSize={12}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#161b22',
                border: '1px solid #30363d',
                borderRadius: '8px',
              }}
              labelStyle={{ color: '#8b949e' }}
              formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
              labelFormatter={formatDate}
            />
            <Line
              type="monotone"
              dataKey="equity"
              stroke="#3fb950"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#3fb950' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
