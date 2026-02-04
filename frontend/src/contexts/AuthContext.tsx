import { createContext, useContext, useState, useEffect, ReactNode, useCallback, useMemo, useRef } from "react";
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
  const isSyncingRef = useRef(false);
  const lastSyncedSubRef = useRef<string | null>(null);

  useEffect(() => {
    const syncUser = async () => {
      if (auth0IsAuthenticated && auth0User && auth0User.sub) {
        // Prevent redundant syncs
        if (isSyncingRef.current || lastSyncedSubRef.current === auth0User.sub) {
          return;
        }

        isSyncingRef.current = true;
        try {
          const token = await (auth0GetAccessTokenSilentlyRef.current ? auth0GetAccessTokenSilentlyRef.current() : "");
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
              // Mark as successfully synced for this sub
              lastSyncedSubRef.current = auth0User.sub || "";

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
        } finally {
          isSyncingRef.current = false;
        }
      }
    };

    syncUser();
  }, [auth0IsAuthenticated, auth0User?.sub]); // Only re-run if auth state or user ID changes

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

  // Use refs to stabilize values for context functions
  const auth0GetAccessTokenSilentlyRef = useRef(auth0GetAccessTokenSilently);
  useEffect(() => {
    auth0GetAccessTokenSilentlyRef.current = auth0GetAccessTokenSilently;
  }, [auth0GetAccessTokenSilently]);

  const getAccessTokenSilently = useCallback(async (): Promise<string> => {
    try {
      if (auth0GetAccessTokenSilentlyRef.current) {
        return await auth0GetAccessTokenSilentlyRef.current();
      }
      return "";
    } catch (error) {
      throw error;
    }
  }, []); // Empty dependencies = stable reference

  // Debug logging
  useEffect(() => {
    console.log("[AuthContext] State changed:", {
      isAuthenticated: auth0IsAuthenticated && !!userId,
      userId,
      auth0IsAuthenticated,
      isLoading: auth0IsLoading
    });
  }, [auth0IsAuthenticated, userId, auth0IsLoading]);

  const contextValue = useMemo<AuthContextType>(() => ({
    isAuthenticated: auth0IsAuthenticated && !!userId,
    userId,
    user: auth0User,
    login,
    logout,
    getAccessTokenSilently,
    isLoading: auth0IsLoading,
  }), [
    auth0IsAuthenticated,
    userId,
    auth0User,
    login,
    logout,
    getAccessTokenSilently,
    auth0IsLoading
  ]);

  return (
    <AuthContext.Provider value={contextValue}>
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

