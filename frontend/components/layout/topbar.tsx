"use client";

import React, { useState } from "react";
import { Search, ChevronDown, Layers, Server, Monitor } from "lucide-react";
import { useAppState } from "@/components/providers";
import { ProfileDialog } from "@/components/profile-dialog";
import { ProfileSwitcher } from "@/components/profile-switcher";
import { useRouter } from "next/navigation";
import Link from "next/link";
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
        <Link href="/" className="flex items-center gap-2.5 mr-8 group cursor-pointer transition-opacity hover:opacity-95">
          <div className="flex items-center justify-center">
            <Image src="/favicon.svg" alt="Job Claw Logo" width={32} height={32} className="w-8 h-8 rounded" />
          </div>
          <span className="font-bold text-lg tracking-tight text-white group-hover:text-[#c8f542] transition-colors">Job-Claw</span>
        </Link>

        <div className="flex-1" />

        {/* Right Controls */}
        <div className="flex items-center gap-4 ml-auto">
          {/* Environment Mode Toggle Segmented Control */}
          <div className="flex items-center bg-black/40 rounded-full border border-white/5 p-1 shadow-[rgba(255,255,255,0.02)_0px_1px_0px_0px_inset]">
            <div className="relative group flex items-center">
              <button 
                onClick={() => apiMode !== 'local' && toggleApiMode()}
                title="Local Mode: Runs discovery and queries directly against localhost endpoints."
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all cursor-pointer ${apiMode === 'local' ? 'bg-card text-foreground shadow-sm border border-white/10' : 'text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent'}`}
              >
                <Monitor className="w-3.5 h-3.5" /> Local
              </button>
              <div className="pointer-events-none absolute top-full mt-2.5 left-1/2 -translate-x-1/2 w-48 rounded-xl bg-zinc-950/95 border border-white/10 p-2.5 text-left text-xs shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 backdrop-blur-xl">
                <p className="font-semibold text-white mb-0.5">Local Mode</p>
                <p className="text-[11px] text-zinc-400 leading-snug">Executes API requests directly on your local machine without remote sync.</p>
              </div>
            </div>

            <div className="relative group flex items-center">
              <button 
                onClick={() => apiMode !== 'server' && toggleApiMode()}
                title="Server Mode: Connects to background workers for automated 15-minute scheduled sweeps."
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all cursor-pointer ${apiMode === 'server' ? 'bg-card text-foreground shadow-sm border border-white/10' : 'text-muted-foreground hover:text-foreground hover:bg-white/5 border border-transparent'}`}
              >
                <Server className="w-3.5 h-3.5" /> Server
              </button>
              <div className="pointer-events-none absolute top-full mt-2.5 left-1/2 -translate-x-1/2 w-52 rounded-xl bg-zinc-950/95 border border-white/10 p-2.5 text-left text-xs shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 backdrop-blur-xl">
                <p className="font-semibold text-white mb-0.5">Server Mode</p>
                <p className="text-[11px] text-zinc-400 leading-snug">Connects to background workers with 15-minute automated discovery sweeps.</p>
              </div>
            </div>
          </div>

          {/* Search Mode Toggle */}
          <div className="relative group flex items-center">
            <button 
              onClick={toggleSearchMode}
              title={isOpenSearch ? "Open Search: Browsing all 221k+ opportunities. Click to switch to Profile Matching." : "Profile Matching Mode: Filtered to your target skills and hubs. Click to browse all jobs."}
              className="flex items-center gap-2 cursor-pointer"
            >
              <span className={`text-xs font-medium hidden md:block transition-colors ${isOpenSearch ? 'text-white' : 'text-muted-foreground group-hover:text-zinc-300'}`}>
                Open Search
              </span>
              <div 
                className={`w-9 h-5 rounded-full relative shadow-[rgba(255,255,255,0.1)_0px_1px_0px_0px_inset] transition-colors ${isOpenSearch ? 'bg-[#c8f542]' : 'bg-card border border-border'}`}
              >
                <div className={`w-4 h-4 rounded-full bg-black absolute top-[1px] transition-transform ${isOpenSearch ? 'translate-x-[18px]' : 'translate-x-[2px] bg-muted-foreground'}`}></div>
              </div>
            </button>
            <div className="pointer-events-none absolute top-full mt-2.5 right-0 w-64 rounded-xl bg-zinc-950/95 border border-white/10 p-2.5 text-left text-xs shadow-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 backdrop-blur-xl">
              <p className="font-semibold text-white mb-0.5">
                {isOpenSearch ? "Open Search Mode" : "Profile-Driven Matching"}
              </p>
              <p className="text-[11px] text-zinc-400 leading-snug">
                {isOpenSearch 
                  ? "Browsing all 221,000+ indexed opportunities. Click to filter exclusively by your candidate profile." 
                  : "Filtered strictly to roles matching your skills and regional tech hubs. Click to browse all opportunities."}
              </p>
            </div>
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
