"use client";

import { create } from "zustand";
import type { AdminPrincipal, ConsoleUser, ConsoleWorkspace } from "./types";

const TOKEN_KEY = "freecadai_admin_token";
const CONSOLE_TOKEN_KEY = "freecadai_console_token";
const CONSOLE_WORKSPACE_KEY = "freecadai_console_workspace_id";

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

type ConsoleState = {
  token: string;
  user: ConsoleUser | null;
  workspaces: ConsoleWorkspace[];
  workspaceId: number | null;
  setToken: (token: string) => void;
  setUser: (user: ConsoleUser | null) => void;
  setWorkspaces: (workspaces: ConsoleWorkspace[]) => void;
  setWorkspaceId: (workspaceId: number | null) => void;
  hydrateAuth: (token: string, user: ConsoleUser, workspaces: ConsoleWorkspace[]) => void;
  logout: () => void;
};

function readConsoleToken() {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(CONSOLE_TOKEN_KEY) || "";
}

function readConsoleWorkspaceId() {
  if (typeof window === "undefined") return null;
  const value = localStorage.getItem(CONSOLE_WORKSPACE_KEY);
  return value ? Number(value) : null;
}

export const useConsoleStore = create<ConsoleState>((set) => ({
  token: readConsoleToken(),
  user: null,
  workspaces: [],
  workspaceId: readConsoleWorkspaceId(),
  setToken: (token) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(CONSOLE_TOKEN_KEY, token);
    }
    set({ token });
  },
  setUser: (user) => set({ user }),
  setWorkspaces: (workspaces) =>
    set((state) => {
      const hasSelected = workspaces.some((workspace) => workspace.id === state.workspaceId);
      const workspaceId = hasSelected ? state.workspaceId : workspaces[0]?.id ?? null;
      if (typeof window !== "undefined") {
        if (workspaceId) localStorage.setItem(CONSOLE_WORKSPACE_KEY, String(workspaceId));
        else localStorage.removeItem(CONSOLE_WORKSPACE_KEY);
      }
      return { workspaces, workspaceId };
    }),
  setWorkspaceId: (workspaceId) => {
    if (typeof window !== "undefined") {
      if (workspaceId) localStorage.setItem(CONSOLE_WORKSPACE_KEY, String(workspaceId));
      else localStorage.removeItem(CONSOLE_WORKSPACE_KEY);
    }
    set({ workspaceId });
  },
  hydrateAuth: (token, user, workspaces) => {
    const workspaceId = workspaces[0]?.id ?? null;
    if (typeof window !== "undefined") {
      localStorage.setItem(CONSOLE_TOKEN_KEY, token);
      if (workspaceId) localStorage.setItem(CONSOLE_WORKSPACE_KEY, String(workspaceId));
    }
    set({ token, user, workspaces, workspaceId });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(CONSOLE_TOKEN_KEY);
      localStorage.removeItem(CONSOLE_WORKSPACE_KEY);
    }
    set({ token: "", user: null, workspaces: [], workspaceId: null });
  }
}));

export function canManageWorkspace(role?: string) {
  return role === "owner" || role === "admin";
}
