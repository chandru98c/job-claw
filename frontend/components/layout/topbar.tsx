"use client";

import React, { useState } from "react";
import { Search, ChevronDown, Layers, Server, Monitor } from "lucide-react";
import { useAppState } from "@/components/providers";
import { ProfileDialog } from "@/components/profile-dialog";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { useRouter } from "next/navigation";

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
          <div className="w-8 h-8 rounded bg-gradient-to-tr from-green-500 to-emerald-400 flex items-center justify-center shadow-[0_0_15px_rgba(34,197,94,0.3)]">
            <Layers className="text-black w-5 h-5" />
          </div>
          <span className="font-bold text-lg tracking-tight text-white">Job-Claw</span>
          <div className="ml-2 px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/20 text-[10px] text-green-400 font-mono flex items-center gap-1.5 hidden sm:flex">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div>
            DB Connected
          </div>
        </div>

        {/* Global Command Palette Mock */}
        <div className="flex-1 flex justify-center max-w-xl mx-auto">
          <div className="relative w-full max-w-md group">
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-zinc-500 group-focus-within:text-green-400 transition-colors">
              <Search className="w-4 h-4" />
            </div>
            <input 
              type="text" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              className="w-full bg-zinc-900/50 border border-white/10 rounded-md pl-10 pr-4 py-1.5 text-sm text-zinc-300 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-green-500/50 focus:border-green-500/50 transition-all hover:bg-zinc-900"
              placeholder="Command Palette (Cmd+K)..."
            />
          </div>
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-4 ml-auto">
          {/* Environment Mode Toggle */}
          <button 
            onClick={toggleApiMode}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-zinc-400 hover:text-white hover:bg-white/5 transition-colors border border-white/5"
            title="Toggle API Environment"
          >
            {apiMode === "local" ? (
              <><Monitor className="w-3.5 h-3.5" /> Local</>
            ) : (
              <><Server className="w-3.5 h-3.5" /> Server</>
            )}
          </button>

          {/* Search Mode Toggle */}
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium hidden md:block transition-colors ${isOpenSearch ? 'text-white' : 'text-zinc-400'}`}>Open Search</span>
            <button 
              onClick={toggleSearchMode}
              className={`w-9 h-5 rounded-full relative shadow-inner transition-colors ${isOpenSearch ? 'bg-green-500 border-green-400' : 'bg-zinc-800 border-white/5'}`}
            >
              <div className={`w-4 h-4 rounded-full bg-white absolute top-[1px] transition-transform ${isOpenSearch ? 'translate-x-[18px]' : 'translate-x-[2px] bg-zinc-500'}`}></div>
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
