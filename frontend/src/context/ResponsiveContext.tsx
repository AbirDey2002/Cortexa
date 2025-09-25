import React, { createContext, useContext, useEffect, useState } from 'react';

interface ResponsiveContextType {
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  windowWidth: number;
}

const ResponsiveContext = createContext<ResponsiveContextType>({
  isMobile: false,
  isTablet: false,
  isDesktop: true,
  windowWidth: typeof window !== 'undefined' ? window.innerWidth : 1024,
});

export const useResponsive = () => useContext(ResponsiveContext);

interface ResponsiveProviderProps {
  children: React.ReactNode;
}

export const ResponsiveProvider: React.FC<ResponsiveProviderProps> = ({ children }) => {
  const [windowWidth, setWindowWidth] = useState<number>(
    typeof window !== 'undefined' ? window.innerWidth : 1024
  );
  
  // Update window width on resize
  useEffect(() => {
    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  // Define breakpoints
  const isMobile = windowWidth < 640; // sm
  const isTablet = windowWidth >= 640 && windowWidth < 1024; // md-lg
  const isDesktop = windowWidth >= 1024;
  
  return (
    <ResponsiveContext.Provider value={{ isMobile, isTablet, isDesktop, windowWidth }}>
      {children}
    </ResponsiveContext.Provider>
  );
};
