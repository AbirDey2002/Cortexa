import { useParams } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { BarChart3, FileText, Zap, Database, TrendingUp } from "lucide-react";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";

export default function UsagePage() {
  const { userId: urlUserId } = useParams<{ userId: string }>();
  const { userId } = useAuth();
  const actualUserId = urlUserId || userId;
  const usageData = {
    testCases: { used: 240, limit: 1000, percentage: 24 },
    requirements: { used: 120, limit: 500, percentage: 24 },
    apiCalls: { used: 8500, limit: 10000, percentage: 85 },
    storage: { used: 2.4, limit: 10, percentage: 24, unit: "GB" },
  };

  const recentActivity = [
    { action: "Generated test cases", count: 24, date: "2 hours ago" },
    { action: "Processed requirements", count: 5, date: "1 day ago" },
    { action: "Exported reports", count: 3, date: "2 days ago" },
  ];

  if (!actualUserId) {
    return null;
  }

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
                  Test Cases
                </CardTitle>
                <FileText className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {usageData.testCases.used.toLocaleString()} / {usageData.testCases.limit.toLocaleString()}
              </div>
              <Progress value={usageData.testCases.percentage} className="mt-2" />
              <p className="text-xs text-muted-foreground mt-2">
                {usageData.testCases.percentage}% of monthly limit
              </p>
            </CardContent>
          </Card>

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
                {usageData.requirements.used.toLocaleString()} / {usageData.requirements.limit.toLocaleString()}
              </div>
              <Progress value={usageData.requirements.percentage} className="mt-2" />
              <p className="text-xs text-muted-foreground mt-2">
                {usageData.requirements.percentage}% of monthly limit
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  API Calls
                </CardTitle>
                <Zap className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {usageData.apiCalls.used.toLocaleString()} / {usageData.apiCalls.limit.toLocaleString()}
              </div>
              <Progress value={usageData.apiCalls.percentage} className="mt-2" />
              <p className="text-xs text-muted-foreground mt-2">
                {usageData.apiCalls.percentage}% of monthly limit
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Storage
                </CardTitle>
                <Database className="w-4 h-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold mb-1">
                {usageData.storage.used} / {usageData.storage.limit} {usageData.storage.unit}
              </div>
              <Progress value={usageData.storage.percentage} className="mt-2" />
              <p className="text-xs text-muted-foreground mt-2">
                {usageData.storage.percentage}% of storage used
              </p>
            </CardContent>
          </Card>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-primary" />
                <CardTitle>Usage Trends</CardTitle>
              </div>
              <CardDescription>Your usage over the last 30 days</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64 flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <BarChart3 className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>Usage chart coming soon</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                <CardTitle>Recent Activity</CardTitle>
              </div>
              <CardDescription>Your latest actions and operations</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {recentActivity.map((activity, index) => (
                  <div key={index} className="flex items-center justify-between p-3 rounded-lg glass">
                    <div>
                      <p className="font-medium text-sm">{activity.action}</p>
                      <p className="text-xs text-muted-foreground">{activity.date}</p>
                    </div>
                    <div className="text-sm font-semibold text-primary">
                      {activity.count}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}

