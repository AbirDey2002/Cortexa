import { useParams, useNavigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { useAuth } from "@/contexts/AuthContext";
import { useEffect } from "react";

export default function UserChatPage() {
  const { userId: urlUserId, usecaseId } = useParams<{ userId: string; usecaseId?: string }>();
  const { userId: authUserId, logout } = useAuth();
  const navigate = useNavigate();

  // If userId in URL doesn't match authenticated userId, redirect to homepage
  useEffect(() => {
    if (!authUserId || (urlUserId && urlUserId !== authUserId)) {
      logout();
      navigate("/");
    }
  }, [authUserId, urlUserId, logout, navigate]);

  if (!authUserId || (urlUserId && urlUserId !== authUserId)) {
    return null; // Will redirect
  }

  return <Layout initialUsecaseId={usecaseId} userId={authUserId} />;
}

