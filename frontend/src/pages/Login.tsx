import { useState } from "react";
import { Button, Field, Notice, inputClass } from "../components/ui";
import { useAuth } from "../state/AuthContext";

export default function Login() {
  const { configured, error, signInGoogle, signInEmail } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <main className="grid min-h-full place-items-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold tracking-tight">HELL UPLOADS</h1>
        <p className="mt-1 text-sm text-mute">Private workspace. Sign in with the owner account.</p>

        {!configured ? (
          <div className="mt-6 space-y-2">
            <Notice tone="warn">
              Firebase isn't configured. Set VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN,
              VITE_FIREBASE_PROJECT_ID and VITE_FIREBASE_APP_ID, then rebuild. See FIREBASE_AUTH_SETUP.md.
            </Notice>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {error && <Notice tone="error">{error}</Notice>}
            <Button className="w-full" onClick={() => void signInGoogle()}>Continue with Google</Button>
            <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); setBusy(true); await signInEmail(email, password); setBusy(false); }}>
              <Field label="Email"><input className={inputClass} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
              <Field label="Password"><input className={inputClass} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
              <Button variant="ghost" className="w-full" type="submit" loading={busy}>Sign in with email</Button>
            </form>
          </div>
        )}
      </div>
    </main>
  );
}
