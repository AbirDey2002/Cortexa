import React, { ReactNode } from "react";
import { useSidebar } from "@/components/ui/sidebar";

interface FloatingInputContainerProps {
  children: ReactNode;
}

export const FloatingInputContainer: React.FC<FloatingInputContainerProps> = ({
  children
}) => {
  const { state: sidebarState } = useSidebar();
  const isSidebarCollapsed = sidebarState === "collapsed";
  
  return (
    <div 
      className={`
        fixed bottom-0 left-0 right-0 z-30
        p-3 sm:p-4 md:p-6 
        border-t border-gray-800 glassmorphism-input
        transition-all duration-300
        ${isSidebarCollapsed ? 'pl-14' : 'pl-16 sm:pl-72 md:pl-80'}
      `}
    >
      {children}
    </div>
  );
};
