import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const TYPES = [['contrato','Contrato'],['nota_fiscal_servico','Nota fiscal'],['aditivo_contratual','Aditivo'],['outros','Outros']];
const LABEL = Object.fromEntries(TYPES);
const fieldValue = (doc, key) => { const v=doc.fields?.[key]?.value; return Array.isArray(v) ? v.join(' a ') : (v ?? '—'); };
const formatConf = n => `${((n ?? 0)*100).toFixed(0)}%`;
function App() {
  const [username,setUsername] = useState('admin');
  const [password,setPassword] = useState('');
  const [token,setToken] = useState('');
  const [role,setRole] = useState('');
  const [batches,setBatches] = useState([]);
  const [selected,setSelected] = useState(null);
  const [uploads,setUploads] = useState([]);
  const [progress,setProgress] = useState(null);
  const [docs,setDocs] = useState([]);
  const [findings,setFindings] = useState([]);
  const [pages,setPages] = useState([]);
  const [tab,setTab] = useState('documents');
  const [query,setQuery] = useState('');
  const [searchResults,setSearchResults] = useState([]);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [reviewDoc,setReviewDoc] = useState(null);
  const [reviewType,setReviewType] = useState('outros');
  const [reviewNote,setReviewNote] = useState('');
  const [reviewApprove,setReviewApprove] = useState(true);
  const canReview = ['admin','revisor'].includes(role);
  async function request(path, options={}) {
    const response=await fetch(API+path,{...options,headers:{...(token?{Authorization:`Bearer ${token}`}:{ }),...(options.headers||{})}});
    const raw=await response.text(); let data;
    try { data=JSON.parse(raw); } catch { data={detail:raw}; }
    if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${response.status}`);
    return data;
  }
  async function refresh(id=selected, authToken=token) {
    if(!authToken) return;
    const options={headers:{Authorization:`Bearer ${authToken}`}};
    const list=await request('/batches',options);
    setBatches(list);
    if(id!=null) {
      const responses=await Promise.all([
        request(`/batches/${id}/progress`,options),
        request(`/batches/${id}/pages`,options),
        request(`/batches/${id}/documents`,options),
        request(`/batches/${id}/findings`,options),
      ]);
      setProgress(responses[0]);setPages(responses[1]);setDocs(responses[2]);setFindings(responses[3]);
    }
  }
  useEffect(()=>{if(!token||selected==null)return;refresh().catch(e=>setError(e.message));const timer=setInterval(()=>refresh().catch(()=>{}),4000);return()=>clearInterval(timer);},[token,selected]);
  async function action(fn, success='Operação concluída') {setBusy(true);setError('');setNotice('');try{await fn();setNotice(success);await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function login(e){e.preventDefault();setError('');try{const body=new URLSearchParams({username,password});const r=await request('/auth/token',{method:'POST',body});setToken(r.access_token);setRole(r.role);setPassword('');await refresh(null,r.access_token);}catch(e){setError(e.message);}}
  function logout(){setToken('');setBatches([]);setSelected(null);setProgress(null);setDocs([]);setFindings([]);setPages([]);setNotice('');}
  async function newBatch(){await action(async()=>{const r=await request('/batches',{method:'POST'});setSelected(r.id);},'Lote criado');}
  async function upload(e){e.preventDefault();if(!uploads.length)return;await action(async()=>{for(const file of uploads){const fd=new FormData();fd.append('file',file);await request(`/batches/${selected}/upload`,{method:'POST',body:fd});}setUploads([]);e.target.reset();},'Arquivo(s) recebido(s)');}
  async function run(){await action(()=>request(`/batches/${selected}/start`,{method:'POST'}),'OCR iniciado. O progresso será atualizado automaticamente.');}
  async function analyze(){await action(()=>request(`/batches/${selected}/analyze`,{method:'POST'}),'Documentos separados e conciliação executada.');setTab('documents');}
  async function search(e){e.preventDefault();if(query.trim().length<2)return;await action(async()=>setSearchResults(await request(`/batches/${selected}/search?q=${encodeURIComponent(query)}`)),'Pesquisa concluída');}
  function review(doc) {
    setReviewDoc(doc);
    setReviewType(doc.document_type);
    setReviewNote('');
    setReviewApprove(true);
    setError('');
    setNotice('');
  }

  async function saveReview(e) {
    e.preventDefault();
    if (!reviewDoc || busy) return;

    const justification = reviewNote.trim();
    if (justification.length < 3) {
      setError('Informe uma justificativa com pelo menos 3 caracteres.');
      return;
    }

    setBusy(true);
    setError('');
    setNotice('');

    try {
      await request(`/documents/${reviewDoc.id}/review`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          document_type: reviewType,
          approve: reviewApprove,
          justification
        })
      });

      await refresh();
      setReviewDoc(null);
      setNotice('Revisão registrada com sucesso.');
    } catch (err) {
      setError('Não foi possível salvar a revisão: ' + err.message);
    } finally {
      setBusy(false);
    }
  }
  async function split(doc){const page=prompt(`Nova primeira página (entre ${doc.start_page+1} e ${doc.end_page}):`);if(!page)return;const note=prompt('Justificativa da divisão:','Separação manual confirmada');if(!note)return;await action(()=>request(`/documents/${doc.id}/split`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({next_start_page:Number(page),justification:note})}),'Documento dividido');}
  async function merge(doc){const options=docs.filter(x=>x.source_file_id===doc.source_file_id&&x.start_page===doc.end_page+1);if(!options.length){setError('Não existe documento imediatamente seguinte no mesmo arquivo');return;}const note=prompt('Justificativa da junção:','Páginas do mesmo documento');if(!note)return;await action(()=>request(`/documents/${doc.id}/merge`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({other_document_id:options[0].id,justification:note})}),'Documentos unidos');}
  async function resolve(finding,decision){const note=prompt('Justificativa para esta decisão:');if(!note)return;await action(()=>request(`/findings/${finding.id}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision,justification:note})}),'Divergência revisada');}
  const pending=docs.filter(d=>d.review_status==='pendente');
  const completed=progress?.pages_total>0&&progress.pages_done===progress.pages_total&&progress.counts.error===0;
  const panel='bg-white border border-slate-200 rounded-2xl p-5 shadow-sm';
  const btn='bg-blue-700 hover:bg-blue-800 text-white rounded-lg px-4 py-2 font-semibold text-sm disabled:opacity-40';
  return <div className="min-h-screen bg-slate-100 text-slate-900">
    <header className="bg-slate-950 text-white"><div className="max-w-7xl mx-auto px-6 py-6 flex items-center justify-between gap-3"><div><h1 className="text-2xl font-extrabold tracking-tight">Concilia <span className="text-sky-400">AI</span></h1><p className="text-slate-400 text-xs tracking-wide mt-1">DOCUMENT AI FACTORY • HACK GARANHUNS TECH 2026</p></div><span className="rounded-full bg-blue-900 border border-blue-700 text-sky-200 px-3 py-1 text-xs">MVP Essencial · Fases 4–7</span></div></header>
    <div className="max-w-7xl mx-auto px-6 py-6"><div className="text-xs bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-5 text-amber-900">Ferramenta de apoio à conferência documental. Não substitui análise jurídica, fiscal ou tributária. Utilize somente documentos sintéticos ou autorizados. Resultados e scores são heurísticos.</div>
      {!token?<form onSubmit={login} className={`${panel} max-w-md mx-auto space-y-4`}><h2 className="text-lg font-bold">Acessar o painel</h2><label className="block text-sm">Usuário<input className="w-full border rounded-lg p-3 mt-1" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label className="block text-sm">Senha<input type="password" className="w-full border rounded-lg p-3 mt-1" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button className={btn}>Entrar</button></form>:
      <div className="grid lg:grid-cols-4 gap-5"><aside className="space-y-5"><section className={panel}><div className="flex items-center justify-between mb-4"><h2 className="font-bold">Lotes</h2><button disabled={busy} onClick={newBatch} className={btn}>+ Novo</button></div><p className="text-xs text-slate-500 mb-3">Perfil: {role}</p><div className="space-y-2 max-h-80 overflow-auto">{batches.map(b=><button key={b.id} onClick={()=>{setSelected(b.id);setTab('documents');setSearchResults([]);}} className={`block text-left w-full border p-3 rounded-xl text-sm ${selected===b.id?'border-blue-600 bg-blue-50':'border-slate-200 hover:bg-slate-50'}`}><strong>Lote #{b.id}</strong><span className="block text-xs text-slate-500 mt-1">{b.status} · {b.total_documents} arquivo(s)</span></button>)}</div><button className="text-sm mt-5 text-slate-500 underline" onClick={logout}>Sair da conta</button></section>
      <section className={panel}><h3 className="font-bold mb-3">Indicadores</h3><div className="grid grid-cols-2 gap-3">{[['Páginas',progress?.pages_total??0],['Documentos',docs.length],['Revisões',pending.length],['Alertas',findings.length]].map(([l,v])=><div key={l} className="bg-slate-50 rounded-xl p-3"><p className="text-2xl font-bold text-blue-700">{v}</p><p className="text-xs text-slate-500">{l}</p></div>)}</div></section></aside>
      <div className="lg:col-span-3 space-y-5">{selected==null?<section className={panel}>Crie ou selecione um lote para começar.</section>:<>
        <section className={panel}><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-bold">Processamento · Lote #{selected}</h2><p className="text-xs text-slate-500">Envie os arquivos, execute o OCR e analise os resultados.</p></div><div className="flex gap-2 flex-wrap"><button className={btn} disabled={busy||!progress?.counts?.pending} onClick={run}>1. Iniciar OCR</button><button className="bg-emerald-700 hover:bg-emerald-800 text-white font-semibold rounded-lg px-4 py-2 text-sm disabled:opacity-40" disabled={busy||!completed||docs.length>0} onClick={analyze}>2. Separar e conciliar</button></div></div><form onSubmit={upload} className="mt-4 flex gap-3 flex-wrap items-center"><input multiple type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff" className="text-xs flex-1 min-w-44" onChange={e=>setUploads([...e.target.files])}/><button disabled={busy||!uploads.length} className={btn}>Enviar {uploads.length||''} arquivo(s)</button></form><div className="w-full h-2.5 rounded-full overflow-hidden bg-slate-200 mt-5"><div className="h-full bg-blue-600 transition-all" style={{width:`${progress?.percent||0}%`}}/></div><div className="flex justify-between text-xs text-slate-500 mt-2"><span>OCR: {progress?.pages_done||0}/{progress?.pages_total||0} páginas</span><span>{progress?.percent||0}% · {progress?.status||'—'}</span></div>{progress?.files?.length>0&&<details className="text-sm mt-3"><summary className="cursor-pointer">Arquivos recebidos ({progress.files.length})</summary>{progress.files.map(f=><div key={f.id} className="text-xs py-1 border-b">{f.filename} · {f.completed_pages}/{f.total_pages} · {f.status}</div>)}</details>}</section>
        <section className={panel}><div className="flex flex-wrap gap-2 border-b pb-3 mb-4">{[['documents',`Documentos (${docs.length})`],['review',`Revisão (${pending.length})`],['findings',`Conciliação (${findings.length})`],['search','Busca OCR'],['pages','Páginas OCR']].map(([key,name])=><button key={key} onClick={()=>setTab(key)} className={`px-3 py-2 text-sm rounded-lg ${tab===key?'bg-blue-700 text-white':'bg-slate-100 hover:bg-slate-200'}`}>{name}</button>)}</div>
          {tab==='documents'&&<div className="space-y-3">{!docs.length?<p className="text-slate-500 text-sm">Após o OCR, clique em “Separar e conciliar” para identificar os documentos.</p>:docs.map(d=><article key={d.id} className="rounded-xl border border-slate-200 p-4"><div className="flex justify-between flex-wrap gap-2"><div><strong>Documento #{d.id}</strong> <span className="text-sm text-blue-800">{LABEL[d.document_type]}</span><p className="text-xs text-slate-500 mt-1">Arquivo #{d.source_file_id} · páginas {d.start_page}–{d.end_page} · confiança {formatConf(d.confidence)}</p></div><span className={`text-xs self-start px-2 py-1 rounded ${d.review_status==='pendente'?'bg-amber-100 text-amber-800':'bg-emerald-100 text-emerald-800'}`}>{d.review_status}</span></div><div className="grid sm:grid-cols-3 gap-2 text-xs bg-slate-50 p-3 rounded mt-3"><div><strong>Fornecedor/CNPJ</strong><p>{fieldValue(d,'supplier_cnpj')}</p></div><div><strong>Valor</strong><p>{fieldValue(d,'value')}</p></div><div><strong>Contrato</strong><p>{fieldValue(d,'contract_id')}</p></div></div><details className="mt-3 text-xs"><summary className="cursor-pointer text-slate-600">Evidências e campos extraídos</summary><p className="mt-2">{d.reasons?.join(' · ')}</p><div className="mt-2 space-y-1">{Object.entries(d.fields||{}).map(([k,v])=><div key={k} className="border-b py-1"><b>{k}</b>: {Array.isArray(v.value)?v.value.join(' a '):v.value} <span className="text-slate-400">· pág. {v.page} · {v.excerpt}</span></div>)}</div></details>{canReview&&<div className="flex flex-wrap gap-2 mt-3"><button className="text-xs border px-3 py-1.5 rounded" onClick={()=>review(d)}>Corrigir / aprovar</button>{d.start_page<d.end_page&&<button className="text-xs border px-3 py-1.5 rounded" onClick={()=>split(d)}>Dividir</button>}<button className="text-xs border px-3 py-1.5 rounded" onClick={()=>merge(d)}>Juntar ao seguinte</button></div>}</article>)}</div>}
          {tab==='review'&&<div className="space-y-3">{!pending.length?<p className="text-slate-500 text-sm">Nenhum documento pendente.</p>:pending.map(d=><div key={d.id} className="border border-amber-200 bg-amber-50 p-4 rounded-xl flex items-center justify-between gap-2"><div><strong>#{d.id} · {LABEL[d.document_type]}</strong><p className="text-xs">Páginas {d.start_page}–{d.end_page} · Confiança {formatConf(d.confidence)}</p><p className="text-xs text-amber-700">{d.reasons?.join('; ')}</p></div>{canReview&&<button className={btn} onClick={()=>review(d)}>Revisar</button>}</div>)}</div>}
          {tab==='findings'&&<div className="space-y-3">{!findings.length?<p className="text-slate-500 text-sm">Nenhuma divergência registrada. Execute a análise ou confira os campos extraídos.</p>:findings.map(f=><article key={f.id} className="border rounded-xl p-4"><div className="flex flex-wrap justify-between gap-2"><strong>{f.rule} · {f.severity.toUpperCase()}</strong><span className={`text-xs rounded px-2 py-1 ${f.status.includes('justificada')?'bg-emerald-100 text-emerald-900':'bg-amber-100 text-amber-900'}`}>{f.status}</span></div><p className="text-sm my-2">{f.message}</p><p className="text-xs text-slate-500">Nota #{f.invoice_id} · Contrato #{f.contract_id||'não identificado'}</p><div className="grid grid-cols-2 gap-3 text-sm mt-2"><div className="bg-slate-50 rounded p-2">Esperado: <b>{f.expected||'—'}</b></div><div className="bg-slate-50 rounded p-2">Encontrado: <b>{f.observed||'—'}</b></div></div><details className="mt-3 text-xs"><summary className="cursor-pointer">Evidências documentais</summary>{f.evidence?.map((ev,i)=><p key={i} className="mt-1 border-l-2 border-blue-300 pl-2">Doc #{ev.document_id}, pág. {ev.page||'?'} — {ev.excerpt||'Campo ausente'}</p>)}</details>{canReview&&!['aceita','rejeitada'].includes(f.status)&&<div className="mt-3 flex gap-2"><button className="border rounded px-3 py-1.5 text-xs" onClick={()=>resolve(f,'aceita')}>Aceitar alerta</button><button className="border rounded px-3 py-1.5 text-xs" onClick={()=>resolve(f,'rejeitada')}>Rejeitar alerta</button></div>}</article>)}</div>}
          {tab==='search'&&<div><form onSubmit={search} className="flex gap-2"><input placeholder="Buscar termo reconhecido pelo OCR" value={query} onChange={e=>setQuery(e.target.value)} className="border p-3 rounded-lg flex-1"/><button className={btn}>Pesquisar</button></form><div className="mt-4 space-y-2">{searchResults.map((r,i)=><div key={i} className="border rounded-xl p-3 text-sm"><b>Arquivo #{r.source_file_id} · página {r.page}</b><p className="text-slate-600 text-xs mt-2 whitespace-pre-wrap">{r.excerpt}</p></div>)}</div></div>}
          {tab==='pages'&&<div className="space-y-2 max-h-[500px] overflow-auto">{pages.map(p=><details key={p.id} className="border rounded-xl p-3 text-sm"><summary className="cursor-pointer">Página {p.page_number} · {p.status} · {p.ocr_method||'—'} · {formatConf(p.ocr_confidence)}</summary><pre className="mt-2 text-xs whitespace-pre-wrap max-h-48 overflow-auto">{p.ocr_text||p.error||'(sem texto)'}</pre></details>)}</div>}
        </section>
      </>}</div></div>}
      {reviewDoc && <div className="fixed inset-0 z-40 bg-slate-950/70 flex items-center justify-center p-4">
        <form onSubmit={saveReview} className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-lg space-y-4">
          <div>
            <h2 className="text-xl font-bold">Revisão humana</h2>
            <p className="text-sm text-slate-500">
              Documento #{reviewDoc.id} · páginas {reviewDoc.start_page}–{reviewDoc.end_page}
            </p>
          </div>

          <label className="block text-sm font-semibold">
            Tipo documental
            <select
              className="block w-full border rounded-lg p-3 mt-1"
              value={reviewType}
              onChange={e => setReviewType(e.target.value)}
            >
              <option value="contrato">Contrato</option>
<option value="nota_fiscal_servico">Nota fiscal</option>
<option value="aditivo_contratual">Aditivo contratual</option>
<option value="outros">Outros</option>
            </select>
          </label>

          <label className="block text-sm font-semibold">
            Justificativa obrigatória
            <textarea
              className="block w-full border rounded-lg p-3 mt-1"
              rows={4}
              maxLength={1000}
              required
              minLength={3}
              value={reviewNote}
              onChange={e => setReviewNote(e.target.value)}
              placeholder="Descreva o que foi conferido no documento."
            />
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={reviewApprove}
              onChange={e => setReviewApprove(e.target.checked)}
            />
            Aprovar a classificação selecionada
          </label>

          <p className="text-xs text-slate-500">
            Desmarcar a aprovação registra o documento como corrigido.
            A revisão será associada ao usuário autenticado.
          </p>

          <div className="flex justify-end gap-3">
            <button type="button" disabled={busy}
              className="border rounded-lg px-4 py-2"
              onClick={() => setReviewDoc(null)}>
              Cancelar
            </button>
            <button type="submit" disabled={busy || reviewNote.trim().length < 3}
              className="bg-blue-700 text-white rounded-lg px-4 py-2 disabled:opacity-40">
              {busy ? 'Salvando...' : 'Salvar revisão'}
            </button>
          </div>
        </form>
      </div>}
      {(error||notice)&&<div role="status" className={`fixed bottom-5 right-5 max-w-lg px-5 py-4 rounded-xl shadow-lg text-sm ${error?'bg-red-800 text-white':'bg-emerald-800 text-white'}`}>{error||notice}<button className="ml-4 underline" onClick={()=>{setError('');setNotice('')}}>Fechar</button></div>}
      <footer className="text-xs text-slate-500 py-6">Concilia AI · MVP experimental · Dados autorizados e revisão humana obrigatória para decisões</footer>
    </div>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);

