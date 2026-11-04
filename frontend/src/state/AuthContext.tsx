import {
  GoogleAuthProvider, onAuthStateChanged, signInWithEmailAndPassword, signInWithPopup, signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setTokenProvider } from "../services/api";
import { getFirebaseAuth, isFirebaseConfigured } from "../services/firebase";
import type { Owner } from "../types/api";

interface AuthState {
  configured: boolean; loading: boolean; owner: Owner | null; error: string | null;
  signInGoogle: () => Promise<void>; signInEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(isFirebaseConfigured);
  const [owner, setOwner] = useState<Owner | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) return;
    setTokenProvider(async () => (auth.currentUser ? auth.currentUser.getIdToken() : null));
    return onAuthStateChanged(auth, async (user: User | null) => {
      setError(null);
      if (!user) { setOwner(null); setLoading(false); return; }
      try {
        setOwner(await api.me());
      } catch (e) {
        setOwner(null);
        setError(e instanceof Error ? e.message : "Sign-in failed");
        await fbSignOut(auth);
      } finally { setLoading(false); }
    });
  }, []);

  const value = useMemo<AuthState>(() => ({
    configured: isFirebaseConfigured, loading, owner, error,
    signInGoogle: async () => {
      const auth = getFirebaseAuth(); if (!auth) return;
      setError(null);
      try { await signInWithPopup(auth, new GoogleAuthProvider()); }
      catch (e) { setError(e instanceof Error ? e.message : "Google sign-in failed"); }
    },
    signInEmail: async (email, password) => {
      const auth = getFirebaseAuth(); if (!auth) return;
      setError(null);
      try { await signInWithEmailAndPassword(auth, email, password); }
      catch { setError("Email or password is incorrect."); }
    },
    signOut: async () => { const a = getFirebaseAuth(); if (a) await fbSignOut(a); },
  }), [loading, owner, error]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
