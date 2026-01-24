import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Bell, Shield, Database, Trash2, LogOut } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";
import { useApi } from "@/lib/utils";
import { requestNotificationPermission } from "@/lib/notifications";
import { APIKeysSettings } from "@/components/settings/APIKeysSettings";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export default function SettingsPage() {
  const { userId: urlUserId } = useParams<{ userId: string }>();
  const { userId, logout } = useAuth();
  const actualUserId = urlUserId || userId;
  const navigate = useNavigate();
  const { toast } = useToast();
  const { apiGet, apiPatch, apiPost, apiDelete } = useApi();

  const [notifications, setNotifications] = useState(true);
  const [hasPassword, setHasPassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  useEffect(() => {
    if (actualUserId) {
      loadSettings();
    }
  }, [actualUserId]);

  const loadSettings = async () => {
    try {
      const user = await apiGet<any>(`/users/${actualUserId}`);
      if (user) {
        setNotifications(user.push_notification !== undefined ? user.push_notification : true);
        setHasPassword(!!user.has_password);
      }
    } catch (error) {
      console.error("Failed to load settings", error);
    }
  };

  const handleNotificationChange = async (checked: boolean) => {
    setNotifications(checked);
    try {
      if (checked) {
        const granted = await requestNotificationPermission();
        if (!granted) {
          setNotifications(false);
          toast({
            title: "Permission denied",
            description: "Please enable notifications in your browser settings.",
            variant: "destructive"
          });
          return;
        }
      }

      await apiPatch(`/users/${actualUserId}`, { push_notification: checked });
      toast({
        title: "Settings updated",
        description: `Push notifications ${checked ? 'enabled' : 'disabled'}.`,
      });
    } catch (error) {
      setNotifications(!checked); // Revert on error
      toast({
        title: "Error",
        description: "Failed to update settings.",
        variant: "destructive"
      });
    }
  };

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast({
        title: "Passwords do not match",
        variant: "destructive"
      });
      return;
    }
    if (newPassword.length < 8) {
      toast({
        title: "Password too short",
        description: "Password must be at least 8 characters.",
        variant: "destructive"
      });
      return;
    }

    setIsChangingPassword(true);
    try {
      await apiPost(`/users/${actualUserId}/change-password`, { new_password: newPassword });
      toast({
        title: "Password updated",
        description: "Your password has been changed successfully.",
      });
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      toast({
        title: "Failed to change password",
        description: "An error occurred. Please try again.",
        variant: "destructive"
      });
    } finally {
      setIsChangingPassword(false);
    }
  };

  const handleDeleteData = async () => {
    try {
      await apiDelete(`/users/${actualUserId}/data`);
      toast({
        title: "Data Deleted",
        description: "All your usecases and related data have been removed.",
      });
      // Redirect or refresh? Maybe just refresh to clear sidebars if any
      window.location.reload();
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete data.",
        variant: "destructive"
      });
    }
  };

  const handleDeleteAccount = async () => {
    try {
      await apiDelete(`/users/${actualUserId}`);
      toast({
        title: "Account Deleted",
        description: "Your account has been successfully deleted. Goodbye.",
      });
      logout();
      navigate("/login");
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete account.",
        variant: "destructive"
      });
    }
  };

  if (!actualUserId) {
    return null;
  }

  return (
    <Layout userId={actualUserId}>
      <div className="container mx-auto px-4 py-8 max-w-3xl">
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold mb-2">Settings</h1>
          <p className="text-muted-foreground">Manage your preferences and data</p>
        </div>

        <div className="space-y-6">
          {/* Notifications */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Bell className="w-5 h-5 text-primary" />
                <CardTitle>Notifications</CardTitle>
              </div>
              <CardDescription>Manage how we communicate with you</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Push Notifications</Label>
                  <p className="text-sm text-muted-foreground">Receive browser notifications for agent responses</p>
                </div>
                <Switch checked={notifications} onCheckedChange={handleNotificationChange} />
              </div>
            </CardContent>
          </Card>

          {/* API Keys (BYOK) */}
          <APIKeysSettings userId={actualUserId} />

          {/* Password Settings (Conditional) */}
          {hasPassword && (
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Shield className="w-5 h-5 text-primary" />
                  <CardTitle>Change Password</CardTitle>
                </div>
                <CardDescription>Update your password (synced with Auth0)</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="new-password">New Password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm Password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
                <Button
                  onClick={handleChangePassword}
                  disabled={isChangingPassword || !newPassword || !confirmPassword}
                >
                  {isChangingPassword ? "Updating..." : "Update Password"}
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Data Management */}
          <Card className="border-destructive/20">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-destructive" />
                <CardTitle className="text-destructive">Data Zone</CardTitle>
              </div>
              <CardDescription>Irreversible actions requiring caution</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label className="text-base">Delete All My Data</Label>
                  <p className="text-sm text-muted-foreground">
                    Removes all usecases, requirements, scenarios, files, etc. Account remains active.
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive/10">
                      <Trash2 className="w-4 h-4 mr-2" />
                      Delete Data
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This action cannot be undone. This will permanently delete all your usecases,
                        files, and generated data from our servers.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={handleDeleteData} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                        Yes, delete my data
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label className="text-base text-destructive">Delete Account</Label>
                  <p className="text-sm text-muted-foreground">
                    Permanently delete your account and all associated data. You will be logged out.
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive">
                      <LogOut className="w-4 h-4 mr-2" />
                      Delete Account
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Are you sure you want to delete your account?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This action is permanent and irreversible. All your data will be lost immediately,
                        and your account will be removed.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={handleDeleteAccount} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                        Yes, delete everything
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
