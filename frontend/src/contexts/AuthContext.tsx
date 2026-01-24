import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useAuth0, User } from "@auth0/auth0-react";

interface AuthContextType {
  isAuthenticated: boolean;
  userId: string | null;
  user: User | undefined;
  login: () => void;
  logout: () => void;
  getAccessTokenSilently: () => Promise<string>;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const SESSION_STORAGE_KEY = "cortexa_user_id";

export function AuthProvider({ children }: { children: ReactNode }) {
  const {
    isAuthenticated: auth0IsAuthenticated,
    user: auth0User,
    loginWithRedirect,
    logout: auth0Logout,
    getAccessTokenSilently: auth0GetAccessTokenSilently,
    isLoading: auth0IsLoading,
  } = useAuth0();

  const [userId, setUserId] = useState<string | null>(() => {
    if (typeof window !== "undefined") {
      return sessionStorage.getItem(SESSION_STORAGE_KEY);
    }
    return null;
  });

  // Listen for storage events (changes from other tabs/windows)
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === SESSION_STORAGE_KEY) {
        setUserId(e.newValue);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  // Listen for custom event (same-tab changes)
  useEffect(() => {
    const handleCustomStorageChange = (e: CustomEvent<string | null>) => {
      setUserId(e.detail);
    };

    window.addEventListener('cortexa:userIdChanged', handleCustomStorageChange as EventListener);
    return () => window.removeEventListener('cortexa:userIdChanged', handleCustomStorageChange as EventListener);
  }, []);

  // Auto-sync user with backend when authenticated
  useEffect(() => {
    const syncUser = async () => {
      if (auth0IsAuthenticated && auth0User) {
        try {
          const token = await auth0GetAccessTokenSilently();
          const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

          const response = await fetch(`${backendUrl}/users/sync`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const data = await response.json();
            if (data.user_id) {
              // Ensure session storage matches backend
              const currentStoredId = sessionStorage.getItem(SESSION_STORAGE_KEY);
              if (currentStoredId !== data.user_id) {
                setUserIdInSession(data.user_id);
              }
            }
          } else {
            console.error("Failed to sync user with backend:", response.status);
          }
        } catch (error) {
          console.error("Error syncing user:", error);
        }
      }
    };

    syncUser();
  }, [auth0IsAuthenticated, auth0User, auth0GetAccessTokenSilently]);

  // Check sessionStorage on focus (for same-tab changes)
  useEffect(() => {
    const checkSessionStorage = () => {
      if (typeof window !== "undefined") {
        const storedUserId = sessionStorage.getItem(SESSION_STORAGE_KEY);
        if (storedUserId !== userId) {
          setUserId(storedUserId);
        }
      }
    };

    // Check on mount
    checkSessionStorage();

    // Check when window gains focus
    window.addEventListener('focus', checkSessionStorage);
    return () => window.removeEventListener('focus', checkSessionStorage);
  }, [userId]);

  const login = () => {
    loginWithRedirect({
      authorizationParams: {
        redirect_uri: window.location.origin + "/callback",
      },
    });
  };

  const logout = () => {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    setUserId(null);
    auth0Logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    });
  };

  const getAccessTokenSilently = async (): Promise<string> => {
    try {
      return await auth0GetAccessTokenSilently();
    } catch (error) {
      throw error;
    }
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: auth0IsAuthenticated && !!userId,
        userId,
        user: auth0User,
        login,
        logout,
        getAccessTokenSilently,
        isLoading: auth0IsLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// Helper function to set userId in sessionStorage (used by Callback page)
export function setUserIdInSession(userId: string) {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(SESSION_STORAGE_KEY, userId);
    // Dispatch custom event to notify AuthContext immediately (same-tab)
    const event = new CustomEvent('cortexa:userIdChanged', { detail: userId });
    window.dispatchEvent(event);
  }
}

