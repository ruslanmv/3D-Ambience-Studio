import { FormEvent, useEffect, useState } from 'react';

type Project = { id:string; name:string; prompt:string; category:string; status:string; sourcePanorama?:string|null };
const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('Calm Forest');
  const [prompt, setPrompt] = useState('A peaceful green forest with a gentle river, no people, seamless 360 panorama');
  const [message, setMessage] = useState('');
  const refresh = async () => setProjects(await (await fetch(`${API}/api/projects`)).json());
  useEffect(() => { refresh(); }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    const res = await fetch(`${API}/api/projects`, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({name,prompt,category:'relax',tags:['nature']})});
    setMessage(res.ok ? 'Project created.' : await res.text()); await refresh();
  }
  async function action(id:string, action:string, body:object={}) {
    const res = await fetch(`${API}/api/projects/${id}/${action}`, {method: action==='validate'?'GET':'POST', headers:{'content-type':'application/json'}, body: action==='validate'?undefined:JSON.stringify(body)});
    setMessage(res.ok ? JSON.stringify(await res.json(), null, 2) : await res.text()); await refresh();
  }

  return <main>
    <header><h1>3D Ambience Studio</h1><p>Create → optimize → validate → publish calm environments.</p></header>
    <section className="card"><h2>New environment</h2><form onSubmit={create}>
      <label>Name<input value={name} onChange={e=>setName(e.target.value)} /></label>
      <label>Prompt<textarea value={prompt} onChange={e=>setPrompt(e.target.value)} /></label>
      <button>Create project</button>
    </form></section>
    <section className="card"><h2>Projects</h2>{projects.map(p=><article key={p.id} className="project">
      <div><strong>{p.name}</strong><small>{p.id} · {p.status}</small><p>{p.prompt}</p></div>
      <div className="actions">
        <button onClick={()=>action(p.id,'generate',{provider:'mock'})}>Mock 360</button>
        <button onClick={()=>action(p.id,'optimize')}>Optimize</button>
        <button onClick={()=>action(p.id,'validate')}>Validate</button>
        <button onClick={()=>action(p.id,'publish',{featured:false})}>Publish</button>
      </div>
    </article>)}</section>
    {message && <section className="card"><h2>Result</h2><pre>{message}</pre></section>}
  </main>;
}
