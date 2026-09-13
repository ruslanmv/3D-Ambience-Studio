/**
 * SYSTEM CONFIGURATION — the same panel as 3D-Avatar-Chatbot's, for image generation.
 *
 * Deliberately a copy, down to the section headings, the provider card grid, the three
 * OllaBridge auth modes, the paired/unpaired boxes and the TEST CONNECTION button. Someone who
 * has configured the avatar app should recognise every control here, because the thing being
 * configured is the same in kind: which service does the work, and how do we authenticate.
 *
 * What differs is only what it configures — images rather than chat — and one honest caveat the
 * avatar app has no need for: OllaBridge's image endpoint accepts no reference image, so on that
 * route the camera guide can only travel as text. The panel says so rather than letting a plate
 * that misses the horizon look like a bug.
 */
import { useCallback, useEffect, useState } from 'react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export type ProviderSpec = {
    id: string;
    label: string;
    icon: string;
    kind: string;
    defaultBaseUrl: string;
    auth: string[];
    supportsGuideImage: boolean;
    notes: string;
};

type Stored = {
    provider: string;
    auth_mode: string;
    base_url: string;
    model: string;
    device_id: string;
    has_api_key: boolean;
    has_pair_token: boolean;
};

const AUTH_LABEL: Record<string, string> = {
    pairing: '📱 Device Pairing',
    apikey: '🔑 API Key',
    'local-trust': '🏠 Local Trust',
};

const AUTH_HINT: Record<string, string> = {
    pairing: 'Enter the OllaBridge pairing code and click Pair.',
    apikey: 'Send an API key as a Bearer token.',
    'local-trust': 'Send no credential at all — for a bridge that trusts its own machine.',
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${API}${path}`, { headers: { 'content-type': 'application/json' }, ...init });
    if (!res.ok) throw new Error((await res.text()) || `${res.status} ${res.statusText}`);
    return res.json() as Promise<T>;
}

export default function Settings({ onSaved }: { onSaved?: (s: Stored) => void }) {
    const [specs, setSpecs] = useState<ProviderSpec[]>([]);
    const [stored, setStored] = useState<Stored | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [pairCode, setPairCode] = useState('');
    const [models, setModels] = useState<string[]>([]);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');
    const [status, setStatus] = useState('');

    const spec = specs.find((s) => s.id === stored?.provider);

    const reload = useCallback(async () => {
        const s = await call<Stored>('/api/settings/generation');
        setStored(s);
        onSaved?.(s);
        return s;
    }, [onSaved]);

    useEffect(() => {
        (async () => {
            try {
                setSpecs(await call<ProviderSpec[]>('/api/image-providers'));
                await reload();
            } catch (e) {
                setError(`Cannot reach the API at ${API} — is it running? (${e})`);
            }
        })();
    }, [reload]);

    async function run(label: string, fn: () => Promise<unknown>) {
        setBusy(label);
        setError('');
        try {
            await fn();
        } catch (e) {
            setError(String(e instanceof Error ? e.message : e));
        } finally {
            setBusy('');
        }
    }

    /** Persist a partial change. Omitted fields keep their stored value — see the API. */
    const patch = (body: Record<string, unknown>) =>
        run('Saving', async () => {
            await call('/api/settings/generation', { method: 'PUT', body: JSON.stringify(body) });
            await reload();
        });

    if (!stored) {
        return (
            <section className="panel">
                <h2 className="panel-title">System configuration</h2>
                {error ? <div className="notice error">{error}</div> : <p className="hint">Loading…</p>}
            </section>
        );
    }

    return (
        <section className="panel">
            <h2 className="panel-title">System configuration</h2>
            {error && (
                <div className="notice error" role="alert">
                    {error}
                </div>
            )}

            <h3 className="config-title">Image provider</h3>
            <div className="card-grid">
                {specs.map((s) => (
                    <label className="pick" key={s.id}>
                        <input
                            type="radio"
                            name="image-provider"
                            value={s.id}
                            checked={stored.provider === s.id}
                            onChange={() => {
                                setModels([]);
                                setStatus('');
                                patch({ provider: s.id });
                            }}
                        />
                        <span className="pick-body">
                            <span className="pick-icon">{s.icon}</span>
                            <span className="pick-name">{s.label}</span>
                        </span>
                    </label>
                ))}
            </div>
            {spec && <p className="hint">{spec.notes}</p>}
            {spec && !spec.supportsGuideImage && (
                <div className="notice info">
                    This route accepts no reference image, so the camera guide is sent as text only — the
                    horizon percentage, the foot anchor and the keep-clear band. Expect a looser fit than a
                    provider that takes the guide as a spatial condition.
                </div>
            )}

            <h3 className="config-title">API configuration</h3>

            {spec && spec.auth.length > 1 && (
                <label className="field">
                    <span className="field-label">Authentication mode</span>
                    <select value={stored.auth_mode} onChange={(e) => patch({ auth_mode: e.target.value })}>
                        {spec.auth.map((mode) => (
                            <option key={mode} value={mode}>
                                {AUTH_LABEL[mode] ?? mode}
                            </option>
                        ))}
                    </select>
                    <p className="hint">{AUTH_HINT[stored.auth_mode]}</p>
                </label>
            )}

            {stored.auth_mode !== 'local-trust' && stored.auth_mode !== 'pairing' && (
                <label className="field">
                    <span className="field-label">
                        API key {stored.has_api_key && <span className="badge">stored</span>}
                    </span>
                    <input
                        type="password"
                        value={apiKey}
                        placeholder={stored.has_api_key ? '•••••••• — type to replace' : 'Enter your API key…'}
                        onChange={(e) => setApiKey(e.target.value)}
                        onBlur={() => apiKey && patch({ api_key: apiKey }).then(() => setApiKey(''))}
                    />
                    <p className="hint">Stored on this machine. Never returned by the API once saved.</p>
                </label>
            )}

            {stored.auth_mode === 'pairing' && (
                <div className="field">
                    <span className="field-label">Device pairing</span>
                    {stored.has_pair_token ? (
                        <div className="paired">
                            <div>
                                <div className="paired-ok">✅ Paired — no code needed</div>
                                <div className="paired-device">Device {stored.device_id || 'unknown'}</div>
                            </div>
                            <button
                                onClick={() =>
                                    run('Unpairing', async () => {
                                        await call('/api/settings/generation/unpair', { method: 'POST' });
                                        await reload();
                                    })
                                }
                                title="Forget this device token and pair again with a new code"
                            >
                                🔓 Unpair
                            </button>
                        </div>
                    ) : (
                        <div className="pair-row">
                            <input
                                type="text"
                                className="pair-code"
                                value={pairCode}
                                maxLength={9}
                                placeholder="Enter pairing code…"
                                onChange={(e) => setPairCode(e.target.value)}
                            />
                            <button
                                className="primary"
                                disabled={!pairCode || !!busy}
                                onClick={() =>
                                    run('Pairing', async () => {
                                        await call('/api/settings/generation/pair', {
                                            method: 'POST',
                                            body: JSON.stringify({ code: pairCode }),
                                        });
                                        setPairCode('');
                                        await reload();
                                    })
                                }
                            >
                                🔗 Pair
                            </button>
                        </div>
                    )}
                </div>
            )}

            <label className="field">
                <span className="field-label">Base URL (root only, no /v1)</span>
                <input
                    type="text"
                    defaultValue={stored.base_url}
                    key={stored.provider + stored.base_url}
                    placeholder={spec?.defaultBaseUrl}
                    onBlur={(e) => e.target.value !== stored.base_url && patch({ base_url: e.target.value })}
                />
            </label>

            <label className="field">
                <span className="field-label">Model</span>
                <div className="pair-row">
                    <select value={stored.model} onChange={(e) => patch({ model: e.target.value })}>
                        <option value="">Select a model…</option>
                        {models.map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                        {stored.model && !models.includes(stored.model) && (
                            <option value={stored.model}>{stored.model}</option>
                        )}
                    </select>
                    <button
                        disabled={!!busy}
                        onClick={() =>
                            run('Fetching models', async () => {
                                const r = await call<{ models: string[] }>('/api/settings/generation/models');
                                setModels(r.models);
                                if (r.models.length === 0) setStatus('The provider returned no models.');
                            })
                        }
                        title="Fetch available models from the provider"
                    >
                        🔄 Fetch Models
                    </button>
                </div>
                <p className="hint">
                    Model ids are configuration, never hard-coded — set whichever your account or bridge has.
                </p>
            </label>

            <div className="field">
                <button
                    style={{ width: '100%' }}
                    disabled={!!busy}
                    onClick={() =>
                        run('Testing', async () => {
                            const r = await call<{ ok: boolean; provider: string; bytes?: number; error?: string }>(
                                '/api/settings/generation/test',
                                { method: 'POST' }
                            );
                            setStatus(
                                r.ok
                                    ? `✅ ${r.provider} answered — ${r.bytes} bytes returned.`
                                    : `❌ ${r.provider}: ${r.error}`
                            );
                        })
                    }
                    title="Generate one small image and report exactly what came back"
                >
                    🔌 Test connection
                </button>
                <div className="test-status" role="status" aria-live="polite">
                    {busy ? `${busy}…` : status}
                </div>
            </div>
        </section>
    );
}
