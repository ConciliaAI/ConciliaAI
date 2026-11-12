import { useEffect, useState } from 'react'
import { api } from '../api'

const MODELOS = { '55': 'NF-e · Produto', '65': 'NFC-e · Consumidor', '57': 'CT-e · Transporte' }
const valor = (v) => v == null ? '—' : String(v)
function formatar(v) {
  if (!v || typeof v !== 'object') return valor(v)
  return Object.entries(v).filter(([, x]) => x != null && x !== '').map(([k, x]) =>
    `${k}: ${typeof x === 'object' ? JSON.stringify(x) : x}`).join(' · ') || '—'
}

export default function Fiscais({ ws, id }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [modelo, setModelo] = useState('')

  useEffect(() => {
    if (!ws && !id) return
    setDados(null)
    const url = id ? `/api/documentos-fiscais/${id}` :
      `/api/ws/${ws}/documentos-fiscais${modelo ? `?modelo=${modelo}` : ''}`
    api.get(url).then(setDados).catch(e => setErro(e.message))
  }, [ws, id, modelo])

  if (erro) return <p role="alert" className="rounded-xl bg-erro-fundo p-4 text-erro">{erro}</p>
  if (!dados) return <p className="text-apoio">Carregando documentos fiscais…</p>

  if (!id) return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-3xl font-bold">Documentos fiscais XML</h1>
        <p className="mt-1 text-sm text-apoio">NF-e (55), NFC-e (65) e CT-e (57) interpretados diretamente do XML, sem OCR.</p>
      </header>
      <label className="flex items-center gap-3 text-sm font-semibold">
        Modelo
        <select className="rounded-xl border border-borda bg-white px-4 py-2" value={modelo} onChange={e => setModelo(e.target.value)}>
          <option value="">Todos</option>
          {Object.entries(MODELOS).map(([m, l]) => <option key={m} value={m}>{l}</option>)}
        </select>
      </label>
      {dados.length === 0 ? (
        <p className="rounded-2xl border border-borda p-6 text-apoio">Nenhum XML desse modelo foi importado. Envie um arquivo XML em “Enviar documentos”.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-borda">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-papel text-xs text-apoio">
              <tr><th className="p-3">Modelo</th><th className="p-3">Número</th><th className="p-3">Emitente</th><th className="p-3">Emissão</th><th className="p-3">Arquivo</th><th className="p-3">Detalhes</th></tr>
            </thead>
            <tbody>{dados.map(d => <tr className="border-t border-borda" key={d.id}>
              <td className="p-3 font-semibold">{MODELOS[d.modelo] || d.modelo}</td>
              <td className="p-3">{valor(d.numero)}</td><td className="p-3">{valor(d.emissor)}</td>
              <td className="p-3">{valor(d.emissao)}</td><td className="p-3">{valor(d.nome_arquivo)}</td>
              <td className="p-3"><a className="font-bold text-confere hover:underline" href={`#fiscal-${d.id}`}>Abrir</a></td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-apoio">A leitura estruturada não comprova autorização perante a SEFAZ. Consulte a validação e o protocolo de cada documento.</p>
    </div>
  )

  const d = dados
  const campos = d.campos || {}
  const xsd = d.validacao?.xsd || 'nao_executada'
  const tributos = campos.tributos || {}
  return (
    <div className="grid gap-5">
      <a href="#fiscais" className="text-sm font-semibold text-confere hover:underline">← Voltar aos XML fiscais</a>
      <header>
        <h1 className="text-3xl font-bold">{MODELOS[d.modelo] || d.tipo} nº {campos.numero || '—'}</h1>
        <p className="mt-1 text-sm text-apoio">Arquivo: {d.nome_arquivo} · Leiaute {d.versao || 'não informado'} · Modelo {d.modelo}</p>
      </header>
      <section className="grid gap-2 rounded-2xl border border-borda p-5">
        <h2 className="font-bold">Validação e autorização</h2>
        <p className="text-sm">Validação XSD: <b>{xsd}</b> · {d.validacao?.motivo_xsd}</p>
        <p className="text-sm">Protocolo XML: <b>{d.protocolo?.codigo || 'não informado'}</b> · {d.protocolo?.mensagem || 'Sem descrição'}</p>
        <p className="text-xs text-apoio">A presença de protocolo no XML não equivale a consulta online de autenticidade na SEFAZ.</p>
        {d.avisos?.length > 0 && <ul className="list-disc pl-5 text-sm text-ambar-texto">{d.avisos.map((x, i) => <li key={i}>{x}</li>)}</ul>}
      </section>
      <section className="grid gap-3 rounded-2xl border border-borda p-5">
        <h2 className="font-bold">Dados principais</h2>
        <dl className="grid gap-2 text-sm">
          {Object.entries(campos).filter(([k]) => !['pagamentos', 'cobranca', 'transporte', 'tributos', 'totais', 'componentes_valor'].includes(k))
            .map(([k, v]) => <div key={k} className="grid grid-cols-1 gap-1 border-b border-borda py-1 last:border-0 sm:grid-cols-[12rem_1fr]">
              <dt className="font-semibold">{k.replaceAll('_', ' ')}</dt><dd className="break-words text-apoio">{formatar(v)}</dd>
            </div>)}
        </dl>
        {Object.keys(tributos).length > 0 && <p className="text-sm">Tributos: {formatar(tributos)}</p>}
      </section>
      {d.itens?.length > 0 && <section className="rounded-2xl border border-borda p-5">
        <h2 className="mb-3 font-bold">Itens ({d.itens.length})</h2>
        <div className="overflow-x-auto"><table className="w-full min-w-[35rem] text-left text-sm">
          <thead><tr><th className="pb-2">Código</th><th>Descrição</th><th>NCM</th><th>CFOP</th><th>Qtd.</th><th>Valor</th></tr></thead>
          <tbody>{d.itens.map((item, i) => <tr key={i} className="border-t border-borda">
            <td className="py-2">{item.codigo}</td><td>{item.descricao}</td><td>{item.ncm}</td>
            <td>{item.cfop}</td><td>{item.quantidade}</td><td>{item.valor_produtos}</td>
          </tr>)}</tbody>
        </table></div>
      </section>}
      {d.referencias?.length > 0 && <section className="rounded-2xl border border-borda p-5">
        <h2 className="mb-2 font-bold">Documentos referenciados</h2>
        {d.referencias.map((r, i) => <p key={i} className="break-all text-sm text-apoio">{formatar(r)}</p>)}
      </section>}
      <details className="rounded-2xl border border-borda p-5">
        <summary className="cursor-pointer font-bold">Rastreabilidade dos campos extraídos</summary>
        <div className="mt-3 grid gap-2">
          {Object.entries(d.proveniencia || {}).map(([campo, p]) =>
            <p className="break-all text-xs text-apoio" key={campo}><b>{campo}</b>: {p.caminho_xml} · original: {p.valor_original}</p>)}
        </div>
      </details>
    </div>
  )
}
