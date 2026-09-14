"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, Database, Activity, Bot } from "lucide-react";
import { useTaskStatus } from "@/hooks/useTaskStatus";
import { useAppState } from "@/components/providers";

export function Sidebar() {
  const pathname = usePathname();
  const status = useTaskStatus();
  const { apiMode } = useAppState();

  const links = [
    { href: "/", label: "Discover", icon: Compass, activeColor: "text-green-400" },
    { href: "/saved-searches", label: "Saved Searches", icon: Database, activeColor: "text-amber-400" },
    { href: "/recommendations", label: "Recommendations", icon: Activity, activeColor: "text-pink-400" },
    { href: "/sources", label: "Source Registry", icon: Database, activeColor: "text-blue-400" },
    { href: "/engines", label: "Pipeline & Engines", icon: Activity, activeColor: "text-purple-400" },
    { href: "/agent", label: "Auto-Apply Agent", icon: Bot, activeColor: "text-orange-400" },
  ];

  return (
    <div className="w-64 border-r border-white/[0.05] bg-black/40 backdrop-blur-sm hidden md:flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-1 py-6 px-4 space-y-1">
        {links.map((link) => {
          const isActive = pathname === link.href;
          const Icon = link.icon;
          
          return (
            <Link 
              key={link.href}
              href={link.href} 
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md font-medium transition-colors ${
                isActive 
                  ? "bg-white/10 text-white border border-white/[0.08] shadow-[0_0_10px_rgba(255,255,255,0.02)]" 
                  : "text-zinc-400 hover:text-white hover:bg-white/5 border border-transparent"
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? link.activeColor : ""}`} />
              {link.label}
            </Link>
          );
        })}
      </div>

      <div className="p-4 border-t border-white/[0.05]">
        <div className="bg-zinc-900/50 border border-white/5 rounded-lg p-4">
          <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">System Status</div>
          <div className="flex items-center gap-2 text-sm text-zinc-300">
            <div className={`w-2 h-2 rounded-full ${status.core_online ? "bg-green-500 animate-pulse" : "bg-red-500"}`}></div>
            Core: {status.core_online ? "Online" : "Offline"}
          </div>
          <div className="flex items-center gap-2 text-sm text-zinc-300 mt-1">
            <div className={`w-2 h-2 rounded-full ${status.worker_status === 'busy' ? "bg-amber-500 animate-pulse" : "bg-zinc-500"}`}></div>
            Worker: {
              apiMode === 'server' 
                ? "Server Delegated" 
                : status.worker_status === 'busy' 
                  ? `Busy (${status.active_tasks})` 
                  : "Idle"
            }
          </div>
        </div>
      </div>
    </div>
  );
}
