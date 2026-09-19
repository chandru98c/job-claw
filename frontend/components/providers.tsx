"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { api } from "@/lib/api";

type AppStateContextType = {
  isOpenSearch: boolean;
  toggleSearchMode: () => void;
  apiMode: "local" | "server";
  toggleApiMode: () => void;
  profileName: string;
  setProfileName: (name: string) => void;
};

const AppStateContext = createContext<AppStateContextType | undefined>(undefined);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [isOpenSearch, setIsOpenSearch] = useState(false);
  const [apiMode, setApiMode] = useState<"local" | "server">("local");
  const [profileName, setProfileNameState] = useState<string>("Loading...");

  // Load state on mount
  useEffect(() => {
    try {
      const savedSearch = localStorage.getItem("jobclaw_open_search");
      if (savedSearch) setIsOpenSearch(savedSearch === "true");
      
      // Fetch profile and worker mode from DB
      const fetchInitialState = async () => {
        try {
          const baseUrl = "http://127.0.0.1:8000";
          
          try {
            const data: any = await api.get("/profiles/me");
            setProfileNameState(data.name);
          } catch (e) {
            console.warn("Failed to load profile", e);
          }

          const modeRes = await fetch(`${baseUrl}/system/worker-mode`);
          if (modeRes.ok) {
            const data = await modeRes.json();
            if (data.mode === "local" || data.mode === "server") {
               setApiMode(data.mode);
            }
          }
        } catch (err) {
          console.error("Failed to fetch initial state", err);
          setProfileNameState("User");
        }
      };
      
      fetchInitialState();
    } catch (e) {
      console.warn("Failed to read AppState", e);
    }
  }, []);

  const toggleSearchMode = () => {
    const newState = !isOpenSearch;
    setIsOpenSearch(newState);
    localStorage.setItem("jobclaw_open_search", String(newState));
  };

  const toggleApiMode = async () => {
    const newMode = apiMode === "local" ? "server" : "local";
    setApiMode(newMode);
    
    try {
      const baseUrl = "http://127.0.0.1:8000";
      await fetch(`${baseUrl}/system/worker-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: newMode }),
      });
    } catch (e) {
      console.warn("Failed to update worker mode", e);
      // Revert on failure
      setApiMode(apiMode);
    }
  };

  const setProfileName = async (name: string) => {
    setProfileNameState(name);
    try {
      await api.put("/profiles/me", { name });
    } catch (e) {
      console.warn("Failed to update profile", e);
    }
  };

  return (
    <AppStateContext.Provider value={{ 
      isOpenSearch, toggleSearchMode,
      apiMode, toggleApiMode,
      profileName, setProfileName
    }}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const context = useContext(AppStateContext);
  if (context === undefined) {
    throw new Error("useAppState must be used within an AppStateProvider");
  }
  return context;
}

// Backward compatibility exports
export const Providers = AppStateProvider;

export function useSearchMode() {
  const { isOpenSearch, toggleSearchMode } = useAppState();
  return { isOpenSearch, toggleSearchMode };
}
