import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
function App() {
  const [username, setUsername] = useState('operador');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState('');
  const [role, setRole] = useState('');
  const [batches, setBatches] = useState([]);
  const [selected, setSelected] = useState(null);
  const [files, setFiles] = useState([]);
  const [progress, setProgress] = useState(null);
  const [pages, setPages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const auth = { Authorization: `Bearer ${token}` };
  async function request(path, options = {}) {
    const res = await fetch(`${BASE}${path}`, options);
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(typeof payload.detail === 'string' ? payload.detail : `Erro HTTP ${res.status}`);
    }
    return res.json();
  }
  async function refresh(sessionToken = token, batchId = selected) {
    if (!sessionToken) return;
    const headers = { Authorization: `Bearer ${sessionToken}` };
    const all = await request('/batches', { headers });
    setBatches(all);
    if (batchId != null) {
      setProgress(await request(`/batches/${batchId}/progress`, { headers }));
      setPages(await request(`/batches/${batchId}/pages`, { headers }));
    }
  }
  useEffect(() => {
    if (!token || selected == null) return;
    refresh().catch(e => setError(e.message));
    const timer = setInterval(() => refresh().catch(e => setError(e.message)), 2500);
    return () => clearInterval(timer);
  }, [token, selected]);
  async function login(event) {
    event.preventDefault(); setError('');
    try {
      const body = new URLSearchParams({ username, password });
      const data = await request('/auth/token', { method: 'POST', body });
      setToken(data.access_token); setRole(data.role); setPassword('');
      await refresh(data.access_token, null);
    } catch (e) { setError(e.message); }
  }
  async function addBatch() {
    setError('');
    try {
      const b = await request('/batches', { method: 'POST', headers: auth });
      setSelected(b.id); await refresh(token, b.id);
    } catch (e) { setError(e.message); }
  }
  async function uploadFiles(event) {
    event.preventDefault();
    if (!files.length || selected == null) return;
    setBusy(true); setError('');
    try {
      for (const file of files) {
        const form = new FormData(); form.append('file', file);
        await request(`/batches/${selected}/upload`, { method: 'POST', headers: auth, body: form });
      }
      setFiles([]); event.target.reset();
      await refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function start() {
    setBusy(true); setError('');
    try { await request(`/batches/${selected}/start`, { method: 'POST', headers: auth }); await refresh(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-slate-100 text-slate-900">
    <header className="bg-slate-950 text-white px-8 py-6"><div className="max-w-6xl mx-auto flex justify-between items-center"><div><h1 className="text-2xl font-bold">Concilia AI</h1><p className="text-slate-300 text-sm">Inteligência documental e conciliação contratual</p></div><span className="text-xs bg-blue-700 rounded-full px-3 py-1">Fase 3 · Upload e OCR</span></div></header>
    <div className="max-w-6xl mx-auto p-6"><div className="bg-amber-50 border border-amber-200 rounded p-4 text-sm mb-6">Apoio à conferência. Não substitui análise jurídica ou tributária. Use somente arquivos sintéticos ou autorizados.</div>
      {!token ? <form onSubmit={login} className="bg-white p-6 rounded-xl shadow max-w-md space-y-4"><h2 className="text-xl font-semibold">Entrar</h2><label className="block text-sm">Usuário<input className="border rounded w-full p-2 mt-1" value={username} onChange={e => setUsername(e.target.value)} required /></label><label className="block text-sm">Senha<input type="password" className="border rounded w-full p-2 mt-1" value={password} onChange={e => setPassword(e.target.value)} required /></label><button className="bg-blue-700 text-white px-5 py-2 rounded">Entrar</button></form>
      : <div className="grid md:grid-cols-3 gap-5"><section className="bg-white rounded-xl shadow p-5"><div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold">Lotes</h2><button onClick={addBatch} className="bg-blue-700 text-white px-3 py-2 rounded text-sm">Novo lote</button></div><p className="text-xs text-slate-500 mb-4">Perfil: {role}</p><div className="space-y-2">{batches.map(b => <button key={b.id} onClick={() => setSelected(b.id)} className={`block w-full text-left border rounded p-3 ${selected === b.id ? 'border-blue-600 bg-blue-50' : ''}`}><strong>Lote #{b.id}</strong><p className="text-xs text-slate-600 mt-1">{b.status} · {b.total_documents} arquivo(s)</p></button>)}{!batches.length && <p className="text-slate-500 text-sm">Crie um lote para começar.</p>}</div><button onClick={() => {setToken('');setBatches([]);setSelected(null);setProgress(null);setPages([])}} className="border px-4 py-2 rounded mt-6 text-sm">Sair</button></section>
      <section className="md:col-span-2 space-y-4">{selected == null ? <div className="bg-white p-6 rounded-xl">Selecione ou crie um lote.</div> : <>
        <form onSubmit={uploadFiles} className="bg-white p-5 rounded-xl shadow"><h2 className="font-semibold mb-3">Enviar PDF ou imagens · Lote #{selected}</h2><input type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff" multiple onChange={e => setFiles([...e.target.files])} className="block w-full text-sm mb-3"/><p className="text-xs text-slate-500 mb-3">Até 40 MB e 500 páginas por arquivo. XML/ZIP ainda não são aceitos nesta fase.</p><button disabled={busy || !files.length} className="bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded">{busy ? 'Aguarde...' : `Enviar ${files.length || ''} arquivo(s)`}</button></form>
        <div className="bg-white p-5 rounded-xl shadow"><div className="flex justify-between"><h2 className="font-semibold">Progresso do OCR</h2><button onClick={start} disabled={busy || !progress || progress.counts.pending === 0} className="bg-emerald-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm">Iniciar processamento</button></div><div className="mt-4 h-3 bg-slate-200 rounded overflow-hidden"><div className="h-full bg-blue-600 transition-all" style={{ width: `${progress?.percent || 0}%` }}/></div><p className="text-sm mt-2">{progress ? `${progress.pages_done}/${progress.pages_total} páginas · ${progress.percent}% · ${progress.status}` : 'Carregando...'}</p><div className="text-xs text-slate-500 mt-2">{progress && `Concluídas: ${progress.counts.ok} · Falhas: ${progress.counts.error} · Pendentes: ${progress.counts.pending} · Processando: ${progress.counts.processing}`}</div><div className="mt-3 space-y-1">{progress?.files.map(f => <p key={f.id} className="border-t py-2 text-sm">{f.filename} — {f.completed_pages}/{f.total_pages} páginas · {f.status}</p>)}</div></div>
        <div className="bg-white p-5 rounded-xl shadow"><h2 className="font-semibold mb-3">Texto extraído por página</h2><div className="space-y-3">{pages.filter(p => p.status === 'ok' || p.status === 'error').map(p => <details key={p.id} className="border rounded p-3"><summary className="cursor-pointer text-sm font-medium">Página {p.page_number} · {p.status} · {p.ocr_method || 'erro'} · Confiança {p.ocr_confidence == null ? '—' : `${(p.ocr_confidence * 100).toFixed(1)}%`}</summary><pre className="whitespace-pre-wrap text-xs mt-3 max-h-48 overflow-auto">{p.ocr_text || p.error || '(nenhum texto reconhecido)'}</pre></details>)}</div></div>
      </>}</section></div>}
      {error && <p role="alert" className="text-red-700 bg-red-50 border border-red-200 p-3 rounded mt-4">{error}</p>}
      <footer className="text-xs text-slate-500 mt-8">Hack Garanhuns Tech 2026 · Desafio 3 · Dados sintéticos para desenvolvimento</footer>
    </div></main>;
}
createRoot(document.getElementById('root')).render(<App />);
