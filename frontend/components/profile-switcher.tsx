"use client";

import React, { useEffect, useState } from "react";
import { UserCircle, Settings, Plus, Check } from "lucide-react";
import { 
  DropdownMenu, 
  DropdownMenuTrigger, 
  DropdownMenuContent, 
  DropdownMenuLabel, 
  DropdownMenuItem, 
  DropdownMenuSeparator,
  DropdownMenuGroup
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useAppState } from "@/components/providers";

type ProfileInfo = {
  id: string;
  name: string;
  is_active?: boolean;
};

export function ProfileSwitcher({ onEditActiveProfile }: { onEditActiveProfile: () => void }) {
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const { profileName, setProfileName } = useAppState();
  const [activeId, setActiveId] = useState<string | null>(null);
  
  useEffect(() => {
    fetchProfiles();
  }, []);
  
  const fetchProfiles = async () => {
    try {
      const data = await api.get<ProfileInfo[]>("/profiles");
      setProfiles(data);
      
      const active = data.find(p => p.is_active);
      if (active) {
        setActiveId(active.id);
        setProfileName(active.name);
      } else if (data.length > 0) {
        // Fallback: If no profile is active but profiles exist, activate the first one
        handleSwitch(data[0].id, data[0].name);
      } else {
        setActiveId(null);
        setProfileName("");
      }
    } catch (e) {
      console.error("Failed to load profiles", e);
    }
  };

  const handleSwitch = async (id: string, name: string) => {
    try {
      await api.post(`/profiles/${id}/activate`, {});
      setActiveId(id);
      setProfileName(name);
      window.dispatchEvent(new Event('profileUpdated'));
      fetchProfiles(); // Refresh the list to ensure is_active flags are fully synced
    } catch (e) {
      console.error("Failed to activate profile", e);
    }
  };

  const handleCreate = async () => {
    const name = prompt("Enter a name for the new profile (e.g. Frontend Dev):");
    if (!name) return;
    
    try {
      const newProfile = await api.post<{id: string, name: string, is_active?: boolean}>("/profiles", { name });
      await handleSwitch(newProfile.id, newProfile.name);
      setTimeout(() => onEditActiveProfile(), 100);
    } catch (e) {
      console.error("Failed to create profile", e);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-2 px-2 py-1.5 rounded-full hover:bg-white/5 transition-colors focus:outline-none focus:ring-1 focus:ring-primary/50">
        <UserCircle className="w-5 h-5 text-muted-foreground" />
        <span className="text-sm font-medium text-muted-foreground hidden sm:block max-w-[120px] truncate">
          {profileName || "Select Profile"}
        </span>
      </DropdownMenuTrigger>
      
      <DropdownMenuContent align="end" className="w-56 bg-background border-border text-white">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground">Switch Profile</DropdownMenuLabel>
          
          {profiles.map(p => (
            <DropdownMenuItem 
              key={p.id} 
              onClick={() => handleSwitch(p.id, p.name)}
              className="flex items-center justify-between cursor-pointer hover:bg-zinc-800"
            >
              <span className="truncate">{p.name}</span>
              {activeId === p.id && <Check className="w-4 h-4 text-primary shrink-0" />}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        
        <DropdownMenuSeparator className="bg-zinc-800" />
        
        <DropdownMenuGroup>
          <DropdownMenuItem onClick={handleCreate} className="cursor-pointer text-primary focus:text-primary hover:bg-zinc-800">
            <Plus className="w-4 h-4 mr-2" />
            Create Profile
          </DropdownMenuItem>
          
          <DropdownMenuItem onClick={onEditActiveProfile} className="cursor-pointer hover:bg-zinc-800" disabled={!activeId}>
            <Settings className="w-4 h-4 mr-2" />
            Edit Current Profile
          </DropdownMenuItem>
        </DropdownMenuGroup>
        
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
