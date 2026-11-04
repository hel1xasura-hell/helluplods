# Firebase Authentication setup
1. Create a Firebase project (free Spark plan is enough).
2. Authentication → Sign-in method: enable **Google** and/or **Email/Password**.
3. Create the owner user yourself in Firebase (Authentication → Users → Add user, or sign in once with Google).
   The app has no sign-up screen, and the backend only accepts the verified email in `OWNER_EMAIL`.
4. Project settings → Your apps → Web app: copy `apiKey`, `authDomain`, `projectId`, `appId` into `frontend/.env`
   (`VITE_FIREBASE_*`).
5. Backend needs only `FIREBASE_PROJECT_ID` to verify tokens. Optionally set `FIREBASE_CREDENTIALS` (service-account
   JSON path) to also check token revocation.
6. Authentication → Settings → Authorized domains: add your deployed frontend domain.
