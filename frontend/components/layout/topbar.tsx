"use client";

import React, { useState } from "react";
import { Search, ChevronDown, Layers, Server, Monitor } from "lucide-react";
import { useAppState } from "@/components/providers";
import { ProfileDialog } from "@/components/profile-dialog";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Button } from "@/components/ui/button";

export function Topbar() {
  const { isOpenSearch, toggleSearchMode, apiMode, toggleApiMode } = useAppState();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/[0.05] bg-black/60 backdrop-blur-md">
      <div className="flex h-14 items-center px-4 md:px-6">
        
        {/* Logo Area */}
        <div className="flex items-center gap-2 mr-8">
          <div className="flex items-center justify-center">
            <Image src="/favicon.svg" alt="Job Claw Logo" width={32} height={32} className="w-8 h-8 rounded" />
          </div>
          <span className="font-bold text-lg tracking-tight text-white">Job-Claw</span>
      
        </div>

        <div className="flex-1" />

        {/* Right Controls */}
        <div className="flex items-center gap-4 ml-auto">
          {/* Environment Mode Toggle Segmented Control */}
          <div className="flex items-center bg-black/40 rounded-full border border-white/5 p-1 shadow-[rgba(255,255,255,0.02)_0px_1px_0px_0px_inset]">
            <button 
              onClick={() => apiMode !== 'local' && toggleApiMode()}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${apiMode === 'local' ? 'bg-card text-foreground shadow-sm border border-white/10' : 'text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent'}`}
            >
              <Monitor className="w-3.5 h-3.5" /> Local
            </button>
            <button 
              onClick={() => apiMode !== 'server' && toggleApiMode()}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${apiMode === 'server' ? 'bg-card text-foreground shadow-sm border border-white/10' : 'text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent'}`}
            >
              <Server className="w-3.5 h-3.5" /> Server
            </button>
          </div>

          {/* Search Mode Toggle */}
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium hidden md:block transition-colors ${isOpenSearch ? 'text-white' : 'text-muted-foreground'}`}>Open Search</span>
            <button 
              onClick={toggleSearchMode}
              className={`w-9 h-5 rounded-full relative shadow-[rgba(255,255,255,0.1)_0px_1px_0px_0px_inset] transition-colors ${isOpenSearch ? 'bg-primary' : 'bg-card border border-border'}`}
            >
              <div className={`w-4 h-4 rounded-full bg-white absolute top-[1px] transition-transform ${isOpenSearch ? 'translate-x-[18px]' : 'translate-x-[2px] bg-muted-foreground'}`}></div>
            </button>
          </div>

          <div className="h-4 w-px bg-white/10 mx-1 hidden sm:block"></div>

          {/* Profile Switcher */}
          <ProfileSwitcher onEditActiveProfile={() => setProfileDialogOpen(true)} />
          <ProfileDialog open={profileDialogOpen} onOpenChange={setProfileDialogOpen} />
        </div>
      </div>
    </header>
  );
}
