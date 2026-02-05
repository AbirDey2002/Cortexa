import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, user, logout } = useAuth();

  // Show loading state while checking authentication
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


  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  // DEBUG: Log the user object to see what claims are present
  console.log("[ProtectedRoute] Current User:", user);

  // Restore actual approval check
  const isApproved = user?.['https://cortexa.ai/approved'] === true;

  if (!isApproved) {
    // Force logout or show "Pending" screen.
    // Ideally, we redirect to homepage where the login modal might show an error, 
    // or we render a specific "Pending Approval" state here.
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center max-w-md p-6 border rounded-lg shadow-lg">
          <h2 className="text-2xl font-bold mb-4">Account Pending Approval</h2>
          <p className="text-muted-foreground mb-6">
            Your account is currently waiting for administrator approval.
            Please contact us at <a href="mailto:abirdey43@gmail.com" className="text-primary hover:underline">abirdey43@gmail.com</a> to request access.
          </p>
          <div className="flex flex-col gap-3 pt-2">
            <button
              onClick={() => logout()}
              className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md font-medium hover:bg-primary/90 transition-all active:scale-[0.98]"
            >
              Return Home
            </button>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

