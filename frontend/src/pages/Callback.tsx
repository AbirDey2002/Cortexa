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
      console.log("%c[FRONTEND-CALLBACK] Starting callback handler", "color: red; font-weight: bold");
      console.log("%c[FRONTEND-CALLBACK] isLoading:", "color: red", isLoading);
      console.log("%c[FRONTEND-CALLBACK] isAuthenticated:", "color: red", isAuthenticated);
      console.log("%c[FRONTEND-CALLBACK] user:", "color: red", user);
      
      if (isLoading) {
        console.log("%c[FRONTEND-CALLBACK] Still loading, waiting...", "color: red");
        return;
      }

      if (!isAuthenticated) {
        console.error("%c[FRONTEND-CALLBACK] Not authenticated, redirecting to homepage", "color: red; font-weight: bold");
        navigate("/", { replace: true });
        return;
      }

      try {
        console.log("%c[FRONTEND-CALLBACK] Getting access token...", "color: red");
        // Get JWT token
        const token = await getAccessTokenSilently();
        console.log("%c[FRONTEND-CALLBACK] Token received (length):", "color: red", token?.length || 0);
        console.log("%c[FRONTEND-CALLBACK] Token preview:", "color: red", token?.substring(0, 50) + "...");

        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
        
        // Check if this is a login or signup attempt
        const loginMode = sessionStorage.getItem("auth0_login_mode");
        const syncUrl = loginMode === "login" 
          ? `${backendUrl}/users/sync-login` 
          : `${backendUrl}/users/sync`;
        
        console.log("%c[FRONTEND-CALLBACK] Login mode:", "color: red", loginMode || "signup (default)");
        console.log("%c[FRONTEND-CALLBACK] Backend URL:", "color: red", backendUrl);
        console.log("%c[FRONTEND-CALLBACK] Sync URL:", "color: red", syncUrl);

        // Sync user to backend
        console.log("%c[FRONTEND-CALLBACK] Sending sync request to backend...", "color: red");
        const response = await fetch(syncUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        });

        console.log("%c[FRONTEND-CALLBACK] Response status:", "color: red", response.status);
        console.log("%c[FRONTEND-CALLBACK] Response ok:", "color: red", response.ok);

        if (!response.ok) {
          let errorText = "";
          try {
            const errorData = await response.json();
            errorText = errorData.detail || JSON.stringify(errorData);
            console.error("%c[FRONTEND-CALLBACK] Response error:", "color: red; font-weight: bold", errorText);
            
            // If login mode and user doesn't exist, redirect to homepage with error
            if (response.status === 404 && loginMode === "login") {
              sessionStorage.removeItem("auth0_login_mode");
              // Store error message to display on homepage
              sessionStorage.setItem("auth0_login_error", errorText || "No account found with this email. Please sign up first.");
              const { logout } = await import("@auth0/auth0-react");
              logout({ logoutParams: { returnTo: window.location.origin } });
              navigate("/", { replace: true });
              return;
            }
          } catch (e) {
            console.error("%c[FRONTEND-CALLBACK] Could not read error text:", "color: red; font-weight: bold", e);
          }
          throw new Error(`Failed to sync user: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const data = await response.json() as { user_id: string };
        console.log("%c[FRONTEND-CALLBACK] Response data:", "color: red", data);

        // Clear login mode flag
        sessionStorage.removeItem("auth0_login_mode");

        // Store user_id in sessionStorage
        if (data.user_id) {
          console.log("%c[FRONTEND-CALLBACK] Setting user_id in session:", "color: red", data.user_id);
          setUserIdInSession(data.user_id);
          console.log("%c[FRONTEND-CALLBACK] Redirecting to dashboard...", "color: red; font-weight: bold");
          // Redirect to user dashboard
          navigate(`/user/${data.user_id}`, { replace: true });
        } else {
          console.error("%c[FRONTEND-CALLBACK] No user_id in response!", "color: red; font-weight: bold");
          // Fallback to homepage if no user_id
          navigate("/", { replace: true });
        }
      } catch (error) {
        console.error("%c[FRONTEND-CALLBACK] Error syncing user:", "color: red; font-weight: bold", error);
        if (error instanceof Error) {
          console.error("%c[FRONTEND-CALLBACK] Error message:", "color: red", error.message);
          console.error("%c[FRONTEND-CALLBACK] Error stack:", "color: red", error.stack);
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

