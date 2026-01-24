import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";
import { setUserIdInSession } from "@/contexts/AuthContext";
import { apiPost } from "@/lib/utils";

export default function Callback() {
  const navigate = useNavigate();
  const { isAuthenticated, getAccessTokenSilently, isLoading, user } = useAuth0();

  useEffect(() => {
    const handleCallback = async () => {

      if (isLoading) {
        return;
      }

      if (!isAuthenticated) {
        navigate("/", { replace: true });
        return;
      }

      try {
        // Get JWT token
        const token = await getAccessTokenSilently();

        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        // Sync user to backend
        const syncUrl = `${backendUrl}/users/sync`;

        const response = await fetch(syncUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          let errorText = "";
          try {
            const errorData = await response.json();
            errorText = errorData.detail || JSON.stringify(errorData);
          } catch (e) {
          }
          throw new Error(`Failed to sync user: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const data = await response.json() as { user_id: string };

        // Clear login mode flag
        sessionStorage.removeItem("auth0_login_mode");

        // Store user_id in sessionStorage
        if (data.user_id) {
          setUserIdInSession(data.user_id);
          // Redirect to user dashboard
          navigate(`/user/${data.user_id}`, { replace: true });
        } else {
          // Fallback to homepage if no user_id
          navigate("/", { replace: true });
        }
      } catch (error) {
        if (error instanceof Error) {
        }
        // On error, still redirect to homepage (user can try again)
        navigate("/", { replace: true });
      }
    };

    handleCallback();
  }, [isAuthenticated, isLoading, getAccessTokenSilently, navigate, user]);

  // Show loading state while processing
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Completing sign in...</p>
      </div>
    </div>
  );
}

