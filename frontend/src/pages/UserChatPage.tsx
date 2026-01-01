import { useParams, useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";
import { useEffect } from "react";

export default function UserChatPage() {
  const { userId: urlUserId, usecaseId } = useParams<{ userId: string; usecaseId?: string }>();
  const { isAuthenticated, userId, isLoading } = useAuth();
  const navigate = useNavigate();

  // Redirect if not authenticated or no userId
  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated || !userId) {
        navigate("/login", { replace: true });
      }
    }
  }, [isAuthenticated, userId, isLoading, navigate]);

  // Show loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render if not authenticated or no userId (will redirect)
  if (!isAuthenticated || !userId) {
    return null;
  }

  return <Layout initialUsecaseId={usecaseId} userId={userId} />;
}

