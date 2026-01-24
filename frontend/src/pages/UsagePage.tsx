import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart3, FileText, Database, TrendingUp, Zap, CheckSquare } from "lucide-react";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from "recharts";

interface UsageMetrics {
  counts: {
    requirements: number;
    scenarios: number;
    test_cases: number;
    test_scripts: number;
  };
  storage: {
    used_kb: number;
    formatted: string;
  };
  trends: Array<{
    date: string;
    requirements: number;
    test_cases: number;
    test_scripts: number;
  }>;
  recent_activity: Array<{
    action: string;
    date: string;
    timestamp: string;
  }>;
}

export default function UsagePage() {
  const { userId: urlUserId } = useParams<{ userId: string }>();
  const { userId, getAccessTokenSilently } = useAuth();
  const actualUserId = urlUserId || userId;

  const [metrics, setMetrics] = useState<UsageMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      if (!actualUserId) return;
      try {
        const token = await getAccessTokenSilently();
        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        const response = await fetch(`${backendUrl}/metrics`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setMetrics(data);
        }
      } catch (error) {
        console.error("Failed to fetch metrics:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
  }, [actualUserId, getAccessTokenSilently]);

  if (!actualUserId) return null;

  if (loading) {
    return (
      <Layout userId={actualUserId}>
        <div className="container mx-auto px-4 py-8 max-w-6xl flex justify-center items-center min-h-[50vh]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </Layout>
    );
  }

  // Fallback if null
  const data = metrics || {
    counts: { requirements: 0, scenarios: 0, test_cases: 0, test_scripts: 0 },
    storage: { used_kb: 0, formatted: "0 KB" },
    trends: [],
    recent_activity: []
  };

  return (
    <Layout userId={actualUserId}>
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="mb-8">
          <h1 className="text-4xl font-display font-bold mb-2">Usage & Analytics</h1>
          <p className="text-muted-foreground">Monitor your usage and track your activity</p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Requirements
                </CardTitle>
                <Database className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {data.counts.requirements}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Requirements processed
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Scenarios
                </CardTitle>
                <FileText className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {data.counts.scenarios}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Scenarios generated
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Test Cases
                </CardTitle>
                <CheckSquare className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {data.counts.test_cases}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Test cases generated
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Storage Est.
                </CardTitle>
                <Database className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {data.storage.formatted}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Estimated DB usage
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          <Card className="md:col-span-2">
            <CardHeader>
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-primary" />
                <CardTitle>Usage Trends (Last 30 Days)</CardTitle>
              </div>
              <CardDescription>Daily generation of Requirements, Test Cases, and Test Scripts</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[300px] w-full">
                {data.trends.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.trends}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                      <XAxis
                        dataKey="date"
                        stroke="hsl(var(--muted-foreground))"
                        fontSize={12}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="hsl(var(--muted-foreground))"
                        fontSize={12}
                        tickLine={false}
                        axisLine={false}
                        allowDecimals={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'hsl(var(--popover))',
                          borderColor: 'hsl(var(--border))',
                          borderRadius: 'var(--radius)',
                          color: 'hsl(var(--popover-foreground))'
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="requirements"
                        name="Requirements"
                        stroke="hsl(var(--primary))"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="test_cases"
                        name="Test Cases"
                        stroke="#10b981"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="test_scripts"
                        name="Test Scripts"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-muted-foreground">
                    No trend data available
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                <CardTitle>Recent Activity</CardTitle>
              </div>
              <CardDescription>Your latest actions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {data.recent_activity.length > 0 ? (
                  data.recent_activity.map((activity, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg glass">
                      <div>
                        <p className="font-medium text-sm">{activity.action}</p>
                        <p className="text-xs text-muted-foreground">{activity.date}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-muted-foreground py-8">No recent activity</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
