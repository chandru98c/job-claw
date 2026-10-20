"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, Database, Activity, Bot, ChevronRight } from "lucide-react";
import { useTaskStatus } from "@/hooks/useTaskStatus";

import { SystemStatusModal } from "@/components/system/system-status-modal";

function workerLabel(status: string, activeTasks: number) {
  if (status === "busy") return `Busy (${activeTasks})`;
  if (status === "idle") return "Idle";
  if (status === "offline") return "Offline";
  return "Unknown";
}

function statusDotClass(status: string) {
  if (status === "busy") return "bg-amber-400 animate-pulse";
  if (status === "idle") return "bg-emerald-400";
  if (status === "offline") return "bg-rose-500";
  return "bg-zinc-500";
}

export function Sidebar() {
  const pathname = usePathname();
  const status = useTaskStatus();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const links = [
    { href: "/", label: "Discover", icon: Compass },
    { href: "/saved-searches", label: "Saved Searches", icon: Database },
    { href: "/recommendations", label: "Recommendations", icon: Activity },
    { href: "/sources", label: "Source Registry", icon: Database },
    { href: "/engines", label: "Pipeline & Engines", icon: Activity },
    { href: "/agent", label: "Auto-Apply Agent", icon: Bot },
  ];

  return (
    <div className="w-56 border-r border-white/[0.05] bg-card/40 backdrop-blur-sm hidden md:flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-1 py-4 px-3 space-y-1 min-h-0 overflow-y-auto">
        {links.map((link) => {
          const isActive = pathname === link.href;
          const Icon = link.icon;

          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-card/50"
              }`}
            >
              <Icon className={`w-5 h-5 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
              <span className="truncate">{link.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="p-3 pb-12 border-t border-white/[0.06] shrink-0">
        <button
          onClick={() => setIsModalOpen(true)}
          className="w-full h-9 px-3 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.08] hover:border-[#c8f542]/30 transition-all flex items-center justify-between group cursor-pointer shadow-sm"
          title="Open System Diagnostics & Running Tasks"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(status.worker_status)}`} />
            <span className="text-xs font-semibold text-zinc-300 group-hover:text-white transition-colors truncate">
              System
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-white/[0.06] text-zinc-400 font-mono font-medium group-hover:text-[#c8f542] transition-colors">
              {status.active_tasks > 0 
                ? `${status.active_tasks} busy` 
                : status.core_online ? "Online" : "Offline"}
            </span>
            <ChevronRight className="w-3.5 h-3.5 text-zinc-500 group-hover:text-[#c8f542] group-hover:translate-x-0.5 transition-all" />
          </div>
        </button>

        <SystemStatusModal 
          open={isModalOpen} 
          onOpenChange={setIsModalOpen} 
          status={status} 
        />
      </div>
    </div>
  );
}
