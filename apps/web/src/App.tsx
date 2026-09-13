/**
 * The artifact wizard.
 *
 * One job: take a designer from a sentence ("moonlit Italian coastal terrace") to a plate that
 * 3D-Avatar-Chatbot can show, without them ever typing a field of view.
 *
 * The Studio owns the technical half — the camera contract, the horizon, the safe zone, the
 * negative prompt. The designer owns the artistic half. Step 3 shows exactly what gets sent,
 * because a hidden prompt is one nobody can debug when a result surprises them.
 *
 * It looks like the avatar app on purpose: same palette, same two fonts, same glass panels and
 * the same checked-card pattern its Settings grid uses. The two are one product.
 */
import { FormEvent, useCallback, useEffect, useState } from 'react';

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type Project = { id: string; name: string; prompt: string; category: string; status: string };
type Profile = {
    name: string;
    width: number;
    height: number;
    fovDeg?: number;
    horizonY?: number;
    footAnchor?: { x: number; y: number };
    safeZone?: { x0: number; x1: number; y0: number; y1: number };
};
type Contract = { file: string; id: string; runtime: string; profiles: Profile[] };
type ProviderInfo = { id: string; role: string; notes: string };
type Prompt = { prompt: string; negativePrompt: string; master: { width: number; height: number } };

const STEPS = ['Describe', 'Target', 'Review prompt', 'Generate', 'Publish'];

/** A single place for fetch + error shape, so every call reports failures the same way. */
async function call<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${API}${path}`, {
        headers: { 'content-type': 'application/json' },
        ...init,
    });
    if (!res.ok) throw new Error((await res.text()) || `${res.status} ${res.statusText}`);
    return res.json() as Promise<T>;
}

export default function App() {
    const [step, setStep] = useState(0);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState('');
    const [result, setResult] = useState('');

    const [projects, setProjects] = useState<Project[]>([]);
    const [project, setProject] = useState<Project | null>(null);

    const [name, setName] = useState('Coastal Terrace');
    const [description, setDescription] = useState(
        'Moonlit Italian coastal terrace overlooking a calm sea, sophisticated and peaceful'
    );
    const [category, setCategory] = useState('relax');

    const [contracts, setContracts] = useState<Contract[]>([]);
    const [contractFile, setContractFile] = useState('avatar-chatbot.json');
    const [profileName, setProfileName] = useState('landscape');
    const [providers, setProviders] = useState<ProviderInfo[]>([]);
    const [provider, setProvider] = useState('mock-backplate');
    const [seed, setSeed] = useState('');

    const [prompt, setPrompt] = useState<Prompt | null>(null);
    // Bumped after each generate so the browser refetches images it has already cached — the
    // URL is stable, so without this the preview shows the previous attempt.
    const [stamp, setStamp] = useState(0);

    const contract = contracts.find((c) => c.file === contractFile);
    const profile = contract?.profiles.find((p) => p.name === profileName);

    const refresh = useCallback(async () => {
        try {
            setProjects(await call<Project[]>('/api/projects'));
        } catch (e) {
            setError(String(e));
        }
    }, []);

    useEffect(() => {
        (async () => {
            try {
                const [cs, ps] = await Promise.all([
                    call<Contract[]>('/api/camera-contracts'),
                    call<ProviderInfo[]>('/api/backplate-providers'),
                ]);
                setContracts(cs);
                setProviders(ps);
                if (cs[0]) {
                    setContractFile(cs[0].file);
                    if (cs[0].profiles[0]) setProfileName(cs[0].profiles[0].name);
                }
            } catch (e) {
                setError(`Cannot reach the API at ${API} — is it running? (${e})`);
            }
            refresh();
        })();
    }, [refresh]);

    /** Wrap an action so every one reports its own failure and always clears the spinner. */
    async function run(label: string, fn: () => Promise<unknown>) {
        setBusy(label);
        setError('');
        try {
            const out = await fn();
            if (out) setResult(JSON.stringify(out, null, 2));
        } catch (e) {
            setError(String(e instanceof Error ? e.message : e));
        } finally {
            setBusy('');
        }
    }

    async function createProject(e: FormEvent) {
        e.preventDefault();
        await run('Creating', async () => {
            const created = await call<Project>('/api/projects', {
                method: 'POST',
                body: JSON.stringify({ name, prompt: description, category, tags: [] }),
            });
            setProject(created);
            await refresh();
            setStep(1);
            return null;
        });
    }

    async function loadPrompt() {
        if (!project) return;
        await run('Compiling prompt', async () => {
            const p = await call<Prompt>(`/api/projects/${project.id}/preview-prompt`, {
                method: 'POST',
                body: JSON.stringify({ provider, contract: contractFile, profile: profileName }),
            });
            setPrompt(p);
            setStep(2);
            return null;
        });
    }

    async function generate() {
        if (!project) return;
        await run('Generating', async () => {
            const body = JSON.stringify({
                provider,
                contract: contractFile,
                profile: profileName,
                seed: seed === '' ? null : Number(seed),
            });
            await call(`/api/projects/${project.id}/generate-plate`, { method: 'POST', body });
            const optimized = await call(`/api/projects/${project.id}/optimize-plate`, { method: 'POST', body });
            setStamp(Date.now());
            setStep(3);
            await refresh();
            return optimized;
        });
    }

    const pct = (v?: number) => (v === undefined ? '—' : `${(v * 100).toFixed(1)}%`);

    return (
        <>
            <header className="topbar">
                <div className="brand">
                    <div className="brand-mark" />
                    <div>
                        <div className="brand-title">3D AMBIENCE STUDIO</div>
                        <div className="brand-sub">Artifact wizard · plates for 3D-Avatar-Chatbot</div>
                    </div>
                </div>
                <div className="topbar-status">{busy ? busy.toUpperCase() + '…' : 'READY'}</div>
            </header>

            <main className="shell">
                <nav className="steps" aria-label="Progress">
                    {STEPS.map((label, i) => (
                        <div
                            key={label}
                            className="step"
                            data-state={i === step ? 'active' : i < step ? 'done' : 'todo'}
                        >
                            <span className="step-index">{i < step ? '✓' : i + 1}</span>
                            <span>{label}</span>
                        </div>
                    ))}
                </nav>

                {error && (
                    <div className="notice error" role="alert">
                        {error}
                    </div>
                )}

                {/* ── 1. Describe ─────────────────────────────────────────────────── */}
                <section className="panel">
                    <h2 className="panel-title">1 · Describe the place</h2>
                    <form onSubmit={createProject}>
                        <label className="field">
                            <span className="field-label">Name</span>
                            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
                        </label>
                        <label className="field">
                            <span className="field-label">Description</span>
                            <textarea value={description} onChange={(e) => setDescription(e.target.value)} required />
                            <p className="hint">
                                Write only the artistic half. The Studio adds the camera, the horizon, the safe
                                zone and the negative prompt — you never type a field of view.
                            </p>
                        </label>
                        <label className="field">
                            <span className="field-label">Category</span>
                            <select value={category} onChange={(e) => setCategory(e.target.value)}>
                                {['relax', 'meditation', 'study', 'sleep', 'nature', 'cozy', 'fantasy', 'focus', 'chill', 'seasonal'].map(
                                    (c) => (
                                        <option key={c} value={c}>
                                            {c}
                                        </option>
                                    )
                                )}
                            </select>
                        </label>
                        <div className="actions end">
                            <button className="primary" disabled={!!busy}>
                                Create project
                            </button>
                        </div>
                    </form>
                    {project && (
                        <div className="notice ok">
                            Working on <strong>{project.name}</strong> · {project.id} · {project.status}
                        </div>
                    )}
                </section>

                {/* ── 2. Target ───────────────────────────────────────────────────── */}
                <section className="panel">
                    <h2 className="panel-title">2 · Which camera is it for</h2>
                    {contracts.length === 0 ? (
                        <div className="notice info">
                            No camera contracts found. The runtime exports one — for the avatar app that is
                            <code> tools/ambience/export-camera-contract.mjs</code> — and it belongs in
                            <code> examples/backplate-camera/</code>.
                        </div>
                    ) : (
                        <>
                            <label className="field">
                                <span className="field-label">Runtime</span>
                                <select
                                    value={contractFile}
                                    onChange={(e) => {
                                        setContractFile(e.target.value);
                                        const next = contracts.find((c) => c.file === e.target.value);
                                        if (next?.profiles[0]) setProfileName(next.profiles[0].name);
                                    }}
                                >
                                    {contracts.map((c) => (
                                        <option key={c.file} value={c.file}>
                                            {c.runtime} ({c.id})
                                        </option>
                                    ))}
                                </select>
                            </label>

                            <span className="field-label">Profile</span>
                            <div className="card-grid">
                                {(contract?.profiles ?? []).map((p) => (
                                    <label className="pick" key={p.name}>
                                        <input
                                            type="radio"
                                            name="profile"
                                            value={p.name}
                                            checked={profileName === p.name}
                                            onChange={() => setProfileName(p.name)}
                                        />
                                        <span className="pick-body">
                                            <span className="pick-name">{p.name}</span>
                                            <span className="pick-meta">
                                                {p.width}×{p.height} · {p.fovDeg}° FOV
                                            </span>
                                        </span>
                                    </label>
                                ))}
                            </div>

                            {profile && (
                                <div className="facts">
                                    <div className="fact">
                                        <div className="fact-key">Horizon</div>
                                        <div className="fact-val">{pct(profile.horizonY)}</div>
                                    </div>
                                    <div className="fact">
                                        <div className="fact-key">Feet</div>
                                        <div className="fact-val">{pct(profile.footAnchor?.y)}</div>
                                    </div>
                                    <div className="fact">
                                        <div className="fact-key">Keep clear</div>
                                        <div className="fact-val">
                                            {pct(profile.safeZone?.x0)}–{pct(profile.safeZone?.x1)}
                                        </div>
                                    </div>
                                    <div className="fact">
                                        <div className="fact-key">Master</div>
                                        <div className="fact-val">
                                            {profile.width}×{profile.height}
                                        </div>
                                    </div>
                                </div>
                            )}
                            <p className="hint">
                                The horizon is not at mid-frame: the runtime's camera is tilted about 1.7° down,
                                which is exactly the kind of detail this wizard exists to keep off your desk.
                            </p>

                            <label className="field" style={{ marginTop: 'var(--spacing-sm)' }}>
                                <span className="field-label">Generator</span>
                                <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                                    {providers.map((p) => (
                                        <option key={p.id} value={p.id}>
                                            {p.id} — {p.role}
                                        </option>
                                    ))}
                                </select>
                                <p className="hint">{providers.find((p) => p.id === provider)?.notes}</p>
                            </label>

                            <label className="field">
                                <span className="field-label">Seed (optional)</span>
                                <input
                                    type="number"
                                    value={seed}
                                    onChange={(e) => setSeed(e.target.value)}
                                    placeholder="leave empty for random"
                                />
                            </label>

                            <div className="actions end">
                                <button className="primary" onClick={loadPrompt} disabled={!project || !!busy}>
                                    Compile prompt
                                </button>
                            </div>
                        </>
                    )}
                </section>

                {/* ── 3. Review ───────────────────────────────────────────────────── */}
                {prompt && (
                    <section className="panel">
                        <h2 className="panel-title">3 · What will be sent</h2>
                        <p className="hint" style={{ marginTop: 0 }}>
                            Shown rather than hidden, so a surprising result has somewhere to be explained.
                        </p>
                        <span className="field-label">Prompt</span>
                        <pre>{prompt.prompt}</pre>
                        <span className="field-label">Negative prompt</span>
                        <pre>{prompt.negativePrompt}</pre>
                        {project && (
                            <div className="preview" style={{ marginTop: 'var(--spacing-sm)' }}>
                                <figure>
                                    <img
                                        src={`${API}/api/projects/${project.id}/guide/${profileName}?v=${stamp}`}
                                        alt="Camera guide"
                                        onError={(e) => ((e.target as HTMLImageElement).style.display = 'none')}
                                    />
                                    <figcaption>Guide — appears after the first generate</figcaption>
                                </figure>
                            </div>
                        )}
                        <div className="actions end">
                            <button className="primary" onClick={generate} disabled={!!busy}>
                                Generate {profile?.width}×{profile?.height}
                            </button>
                        </div>
                    </section>
                )}

                {/* ── 4. Result ───────────────────────────────────────────────────── */}
                {step >= 3 && project && (
                    <section className="panel">
                        <h2 className="panel-title">4 · Result</h2>
                        <div className="preview">
                            <figure>
                                <img
                                    src={`${API}/api/projects/${project.id}/plate/${profileName}?v=${stamp}`}
                                    alt="Generated plate"
                                />
                                <figcaption>Plate · {profileName}</figcaption>
                            </figure>
                            <figure>
                                <img
                                    src={`${API}/api/projects/${project.id}/guide/${profileName}?v=${stamp}`}
                                    alt="Camera guide"
                                />
                                <figcaption>Guide it was generated against</figcaption>
                            </figure>
                        </div>
                        <p className="hint">
                            Compare the two. The plate's horizon should sit on the guide's red line — if it does
                            not, the generator ignored the conditioning image rather than the guide being wrong.
                        </p>
                        <div className="actions end">
                            <button
                                onClick={() =>
                                    project &&
                                    run('Validating', () => call(`/api/projects/${project.id}/validate`))
                                }
                                disabled={!!busy}
                            >
                                Validate
                            </button>
                            <button
                                className="primary"
                                onClick={() =>
                                    project &&
                                    run('Publishing', async () => {
                                        const out = await call(`/api/projects/${project.id}/publish`, {
                                            method: 'POST',
                                            body: JSON.stringify({ featured: false }),
                                        });
                                        setStep(4);
                                        return out;
                                    })
                                }
                                disabled={!!busy}
                            >
                                Publish
                            </button>
                        </div>
                    </section>
                )}

                {result && (
                    <section className="panel">
                        <h2 className="panel-title">Output</h2>
                        <pre>{result}</pre>
                    </section>
                )}

                <section className="panel">
                    <h2 className="panel-title">Projects</h2>
                    {projects.length === 0 && <p className="hint">Nothing yet.</p>}
                    {projects.map((p) => (
                        <article className="project" key={p.id}>
                            <div>
                                <strong>{p.name}</strong>
                                <small>
                                    {p.id} · {p.category}
                                </small>
                            </div>
                            <div className="actions" style={{ margin: 0 }}>
                                <span className="badge">{p.status}</span>
                                <button
                                    onClick={() => {
                                        setProject(p);
                                        setPrompt(null);
                                        setStep(1);
                                    }}
                                >
                                    Resume
                                </button>
                            </div>
                        </article>
                    ))}
                </section>
            </main>
        </>
    );
}
