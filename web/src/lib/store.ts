"use client";

import { create } from "zustand";
import type { AdminPrincipal } from "./types";

const TOKEN_KEY = "freecadai_admin_token";

type AppState = {
  token: string;
  principal: AdminPrincipal | null;
  workspaceId: number | null;
  setToken: (token: string) => void;
  setPrincipal: (principal: AdminPrincipal | null) => void;
  setWorkspaceId: (workspaceId: number | null) => void;
  logout: () => void;
};

function readToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export const useAppStore = create<AppState>((set) => ({
  token: readToken(),
  principal: null,
  workspaceId: null,
  setToken: (token) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(TOKEN_KEY, token);
    }
    set({ token });
  },
  setPrincipal: (principal) => set({ principal }),
  setWorkspaceId: (workspaceId) => set({ workspaceId }),
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
    }
    set({ token: "", principal: null, workspaceId: null });
  }
}));

export function canOperate(role?: string) {
  return role === "owner" || role === "operator";
}

export function canManageAdmins(role?: string) {
  return role === "owner";
}
