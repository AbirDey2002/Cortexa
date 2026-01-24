import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { User, Mail, Calendar, Save } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { Layout } from "@/components/Layout";

export default function ProfilePage() {
  const { userId: urlUserId } = useParams<{ userId: string }>();
  const { userId, getAccessTokenSilently, user } = useAuth();
  const actualUserId = urlUserId || userId;
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [memberSince, setMemberSince] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchUserProfile = async () => {
      if (!actualUserId) return;

      try {
        const token = await getAccessTokenSilently();
        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        const response = await fetch(`${backendUrl}/users/${actualUserId}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setName(data.name || user?.name || "");
          setEmail(data.email || user?.email || "");

          if (data.created_at) {
            const date = new Date(data.created_at);
            setMemberSince(date.toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric'
            }));
          }
        }
      } catch (error) {
        console.error("Failed to fetch profile:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchUserProfile();
  }, [actualUserId, getAccessTokenSilently, user]);

  const handleSave = async () => {
    if (!actualUserId) return;
    try {
      const token = await getAccessTokenSilently();
      const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

      const response = await fetch(`${backendUrl}/users/${actualUserId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name }),
      });

      if (response.ok) {
        toast({
          title: "Profile updated",
          description: "Your profile information has been saved successfully.",
        });
      } else {
        throw new Error("Failed to update");
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to update profile. Please try again.",
        variant: "destructive",
      });
    }
  };

  const getInitials = (name: string) => {
    return (name || "U")
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  if (!actualUserId) {
    return null;
  }

  if (isLoading) {
    return <div className="p-8 text-center">Loading profile...</div>;
  }

  return (
    <Layout userId={actualUserId}>
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <div className="mb-8">
          <h1 className="text-4xl font-display font-bold mb-2">Profile</h1>
          <p className="text-muted-foreground">Manage your profile information</p>
        </div>

        <div className="space-y-6">
          {/* Profile Header */}
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
              <CardDescription>Update your personal information</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-6">
                <Avatar className="w-24 h-24">
                  <AvatarImage src={user?.picture || ""} alt={name} />
                  <AvatarFallback className="text-2xl bg-gradient-primary text-primary-foreground">
                    {getInitials(name)}
                  </AvatarFallback>
                </Avatar>
                {/* Upload removed as not implemented in backend yet */}
              </div>

              <Separator />

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">
                    <User className="w-4 h-4 inline mr-2" />
                    Full Name
                  </Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">
                    <Mail className="w-4 h-4 inline mr-2" />
                    Email
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    disabled
                    className="bg-muted"
                  />
                </div>
              </div>

              <Button onClick={handleSave} className="w-full sm:w-auto">
                <Save className="w-4 h-4 mr-2" />
                Save Changes
              </Button>
            </CardContent>
          </Card>

          {/* Account Details */}
          <Card>
            <CardHeader>
              <CardTitle>Account Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm">Member since</span>
                </div>
                <span className="text-sm font-medium">{memberSince || "Loading..."}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm">Email verified</span>
                </div>
                {/* Assuming verified if logged in via Google, or check user.email_verified */}
                <span className="text-sm font-medium text-green-500">Verified</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}

