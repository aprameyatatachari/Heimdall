import { createContext } from "react";

import type { UserResponse } from "@/api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthContextValue {
  status: AuthStatus;
  user: UserResponse | null;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
