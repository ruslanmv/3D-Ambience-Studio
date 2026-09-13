/// <reference types="vite/client" />

/**
 * The standard Vite ambient declarations, missing from the original scaffold.
 *
 * Without them `tsc` rejects two things the app has always done: reading
 * `import.meta.env.VITE_API_BASE_URL`, and importing `./styles.css` for its side effect. Both
 * errors were present on a clean checkout before the wizard existed — `npm run build` runs
 * `tsc && vite build`, so the build has never passed.
 */
