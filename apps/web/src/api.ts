/**
 * Where the API lives, decided once.
 *
 * Two deployments, two answers. In development the web app is served by Vite on :5173 and the
 * API runs separately on :8000, so an absolute base URL is required. In the Hugging Face Space
 * one process serves both — FastAPI serves the built bundle — so the base must be empty and
 * every call must be same-origin, or the browser would ask localhost:8000 on the visitor's own
 * machine and fail with a CORS error that looks like a server outage.
 *
 * The subtlety that forced this file: `import.meta.env.VITE_API_BASE_URL || fallback` can never
 * express "same origin", because the empty string is falsy and collapses back to the fallback.
 * So an absent variable and an empty one have to be told apart, and `undefined` is the only
 * value that means "nobody said".
 */
const configured = import.meta.env.VITE_API_BASE_URL;

export const API = configured === undefined ? 'http://localhost:8000' : configured;
