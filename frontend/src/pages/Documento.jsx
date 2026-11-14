import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'
import { nomeDocumento, pasta } from '../documentos'

// Layout do Figma "Documento - Nota com divergência": página à esquerda; divergência, confiança e campos à direita.
const NOMES = {
  numero: 'Número', nome_prestador: 'Prestador', cnpj_prestador: 'CNPJ do prestador', cnpj_tomador: 'CNPJ do tomador',
  objeto: 'Objeto', valor_mensal: 'Valor mensal', valor_total: 'Valor total', vigencia_inicio: 'Início da vigência',
  vigencia_fim: 'Fim da vigência', contrato_ref: 'Contrato', valor_adicional: 'Acréscimo mensal', data_emissao: 'Emissão',
  competencia: 'Competência', descricao: 'Serviço', valor: 'Valor',
}
const SEVERIDADE = { critica: ['Crítica', 'bg-erro text-white'], alta: ['Alta', 'bg-erro-fundo text-erro'], media: ['Média', 'bg-ambar-fundo text-ambar-texto'] }
const SITUACAO = { confirmado: ['Pronto', 'bg-nevoa text-tinta'], revisao: ['Em revisão', 'bg-ambar-fundo text-ambar-texto'], aguardando: ['Aguardando', 'bg-papel text-apoio'] }

const brl = (v) => (v == null || v === '' ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }))
const data = (v) => (v && /^\d{4}-\d{2}-\d{2}/.test(v) ? new Date(v.slice(0, 10) + 'T00:00').toLocaleDateString('pt-BR') : v)
function valorCampo(k, v) {
  if (v == null || v === '') return '—'
  if (k.startsWith('cnpj') && String(v).length === 14) return String(v).replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5')
  if (k.startsWith('valor')) return brl(v)
  if (k.startsWith('vigencia') || k === 'data_emissao') return data(v)
  return String(v)
}
const dinheiro = (texto) => { const m = String(texto || '').match(/R\$\s*([\d.]+,\d{2})/); return m ? +m[1].replace(/\./g, '').replace(',', '.') : null }

function Divergencia({ div, podeDecidir, aoDecidir }) {
  const [texto, setTexto] = useState('')
  const [sev, corSev] = SEVERIDADE[div.severidade] || ['', '']
  const aberta = div.status === 'aberta'
  const limite = dinheiro(div.esperado)
  const valor = div.nota_valor
  const caixas = div.regra === 'VALOR_DIVERGENTE' && limite != null && valor != null
    ? [['Contrato + aditivo', brl(limite), ''], ['Nota', brl(valor), 'text-erro'], ['Diferença', `+ ${brl(valor - limite)}`, 'text-erro']]
    : [['O contrato prevê', div.esperado || '—', ''], ['A nota apresenta', div.encontrado || '—', 'text-erro']]
  return (
    <section className={`rounded-2xl border p-5 ${aberta ? 'border-erro/30 bg-erro-fundo/60' : 'border-borda bg-white'}`}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-bold"><span className="text-erro" aria-hidden="true">⚠</span>{div.titulo}</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${corSev}`}>{sev}</span>
      </div>
      <p className="mt-1.5 text-[0.8125rem] text-apoio">{div.mensagem}</p>
      <div className={`mt-4 grid gap-2.5 ${caixas.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
        {caixas.map(([r, v, cor]) => (
          <div key={r} className="rounded-xl border border-borda bg-white px-3 py-2.5">
            <p className="text-[0.6875rem] text-apoio">{r}</p>
            <p className={`text-[0.9375rem] font-bold ${caixas.length === 3 ? 'truncate' : 'break-words'} ${cor}`} title={v}>{v}</p>
          </div>
        ))}
      </div>
      {aberta ? (
        <>
          {podeDecidir && (
            <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} aria-label="Justificativa ou motivo"
                      placeholder="Justificativa (para aprovar) ou motivo (para rejeitar). Vai para o relatório."
                      className="mt-4 w-full rounded-xl border border-borda bg-white px-3 py-2 text-sm outline-none focus:border-confere focus:ring-2 focus:ring-confere/25" />
          )}
          <div className={`mt-3 grid grid-cols-2 gap-2.5 ${podeDecidir ? '' : 'pointer-events-none opacity-50'}`}>
            <button onClick={() => aoDecidir(div, 'aprovar', texto)} className="h-10 rounded-full bg-confere text-sm font-bold text-white hover:bg-[#2559e0]">Aprovar com justificativa</button>
            <button onClick={() => aoDecidir(div, 'rejeitar', texto)} disabled={texto.trim().length < 3}
                    title={texto.trim().length < 3 ? 'Escreva o motivo para rejeitar' : undefined}
                    className="h-10 rounded-full border-2 border-erro bg-white text-sm font-bold text-erro hover:bg-erro-fundo disabled:opacity-50">Rejeitar</button>
          </div>
          {!podeDecidir && <p className="mt-2 text-xs text-apoio">Só revisor ou administrador decide divergências.</p>}
        </>
      ) : (
        <p className="mt-4 text-[0.8125rem] text-apoio">
          {div.status === 'aprovada' ? 'Aprovada' : 'Rejeitada'} por {div.decidido_por}{div.comentario ? `: “${div.comentario}”` : '.'}
          {podeDecidir && <button onClick={() => aoDecidir(div, 'reabrir', '')} className="ml-2 font-bold text-tinta underline">Reabrir</button>}
        </p>
      )}
    </section>
  )
}

export default function Documento({ ws, id, perfil, aoMudar }) {
  const [doc, setDoc] = useState(null)
  const [nota, setNota] = useState(null)
  const [pagina, setPagina] = useState(0)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState(null)
  const [confirmarExcluir, setConfirmarExcluir] = useState(false)
  const podeDecidir = perfil === 'revisor' || perfil === 'admin'

  const carregar = useCallback(async () => {
    try {
      const d = await api.get(`/api/docs/${id}`)
      setDoc(d)
      // Nota fiscal lida deste documento (para mostrar a divergência com o contrato).
      const notas = ws ? await api.get(`/api/ws/${ws}/notas`) : []
      const n = notas.find((x) => x.doc_id === d.id)
      setNota(n ? await api.get(`/api/notas/${n.id}`) : null)
    } catch (e) {
      setErro(e.message)
    }
  }, [id, ws])

  useEffect(() => { carregar() }, [carregar])

  async function decidir(div, acao, comentario) {
    try {
      const r = await api.post(`/api/divergencias/${div.id}/decisao`, { acao, comentario })
      setAviso({ texto: r.msg })
      await carregar()
      aoMudar?.()
    } catch (e) {
      setAviso({ texto: e.message, erro: true })
    }
  }

  async function corrigirSubtipo(subtipo) {
    try {
      const r = await api.post(`/api/docs/${id}/decisao`, { acao: 'corrigir_subtipo', subtipo })
      setAviso({ texto: r.msg })
      await carregar()
      aoMudar?.()
    } catch (e) {
      setAviso({ texto: e.message, erro: true })
    }
  }

  async function excluir() {
    if (!confirmarExcluir) { setConfirmarExcluir(true); setTimeout(() => setConfirmarExcluir(false), 4000); return }
    try {
      await api.excluir(`/api/docs/${id}`)
      aoMudar?.()
      window.location.hash = 'documentos'
    } catch (e) {
      setAviso({ texto: e.message, erro: true })
    }
  }

  if (erro) {
    return (
      <div className="grid gap-4">
        <a href="#documentos" className="text-sm font-semibold text-tinta">← Documentos</a>
        <p className="rounded-2xl bg-erro-fundo p-6 text-erro">{erro}</p>
      </div>
    )
  }
  if (!doc) return <p className="text-apoio">Carregando…</p>

  const pags = doc.paginas || []
  const atual = pags[Math.min(pagina, pags.length - 1)]
  const campos = doc.dados?.campos || {}
  const numero = campos.numero ? ` nº ${campos.numero}` : ''
  const [situacao, corSit] = SITUACAO[doc.status] || [doc.status, 'bg-papel text-apoio']
  const abertas = (nota?.divergencias || []).filter((d) => d.status === 'aberta')
  const divs = (nota?.divergencias || []).map((d) => ({ ...d, nota_valor: nota.valor }))
  const motivoConf = (doc.sinais || []).filter((s) => !/^Página \d|Primeira página/.test(s)).slice(0, 2).join('; ')

  return (
    <div className="grid grid-cols-1">
      <p className="text-[0.8125rem] text-apoio">
        <a href="#documentos" className="hover:text-tinta hover:underline">Documentos</a> / {pasta(doc.tipo)} / {nomeDocumento(doc).split(' · ')[0]}
      </p>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-4">
        <h1 className="flex min-w-0 flex-wrap items-center gap-3 text-[1.75rem] leading-[1.25] font-bold">
          <span className="truncate">{doc.tipo}{numero}</span>
          {abertas.length > 0
            ? <span className="rounded-full bg-erro-fundo px-2.5 py-1 font-sans text-xs font-bold text-erro">Divergência</span>
            : <span className={`rounded-full px-2.5 py-1 font-sans text-xs font-bold ${corSit}`}>{situacao}</span>}
        </h1>
        <div className="flex gap-3">
          <a href={`/api/docs/${doc.id}/pdf`} className="grid h-11 place-items-center rounded-full border-2 border-confere px-6 text-sm font-bold text-tinta hover:bg-nevoa">Baixar PDF</a>
          {podeDecidir && (
            <button onClick={excluir}
                    className={`h-11 rounded-full border-2 px-6 text-sm font-bold ${confirmarExcluir ? 'border-erro bg-erro text-white' : 'border-erro text-erro hover:bg-erro-fundo'}`}>
              {confirmarExcluir ? 'Clique de novo para excluir' : 'Excluir'}
            </button>
          )}
        </div>
      </div>

      {aviso && (
        <p className={`mt-4 flex items-start justify-between gap-4 rounded-xl px-4 py-3 text-sm ${aviso.erro ? 'bg-erro-fundo text-erro' : 'bg-nevoa text-tinta'}`} role="status">
          {aviso.texto}
          <button onClick={() => setAviso(null)} aria-label="Fechar aviso"><Icone nome="fechar" className="size-4" /></button>
        </p>
      )}

      {/* Figma: página 532 à esquerda, coluna 274 à direita (proporção ~ 1.9 : 1), espaço 12. */}
      <div className="mt-5 grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)]">
        <section className="grid gap-3 rounded-2xl bg-papel p-4 sm:p-6">
          <div className="grid min-h-[30rem] place-items-center">
            {atual
              ? <img src={`/api/paginas/${atual.id}/imagem?largura=900`} alt={`Página ${pagina + 1} de ${pags.length}`} className="max-h-[48rem] w-full max-w-[38rem] rounded-md bg-white object-contain shadow-sm" />
              : <p className="text-sm text-suave">Sem imagem da página.</p>}
          </div>
          <div className="flex items-center justify-center gap-3 text-[0.8125rem] text-apoio">
            <button onClick={() => setPagina((p) => Math.max(0, p - 1))} disabled={pagina === 0}
                    className="grid size-8 place-items-center rounded-full bg-white font-bold disabled:opacity-40" aria-label="Página anterior">‹</button>
            <span>Página {Math.min(pagina, pags.length - 1) + 1} de {pags.length} · página {atual?.n} do lote · confiança {atual?.conf}%</span>
            <button onClick={() => setPagina((p) => Math.min(pags.length - 1, p + 1))} disabled={pagina >= pags.length - 1}
                    className="grid size-8 place-items-center rounded-full bg-white font-bold disabled:opacity-40" aria-label="Próxima página">›</button>
          </div>
        </section>

        <div className="grid gap-4">
          {divs.map((d) => <Divergencia key={d.id} div={d} podeDecidir={podeDecidir} aoDecidir={decidir} />)}

          <section className="rounded-2xl border border-borda p-5">
            <div className="flex items-end justify-between">
              <h2 className="text-[0.9375rem] font-bold">Confiança da leitura</h2>
              <p className={`font-titulo text-[1.75rem] leading-none font-bold ${doc.conf >= doc.limiar ? 'text-confere' : 'text-ambar-texto'}`}>{doc.conf}%</p>
            </div>
            <div className="mt-3 h-1.5 rounded-full bg-papel">
              <div className={`h-full rounded-full ${doc.conf >= doc.limiar ? 'bg-confere' : 'bg-ambar'}`} style={{ width: `${doc.conf}%` }} />
            </div>
            <p className="mt-3 text-[0.8125rem] text-apoio">
              {motivoConf ? `Por quê: ${motivoConf}. ` : ''}
              {doc.conf >= doc.limiar ? `Acima de ${doc.limiar}%, não precisa de revisão.` : `Abaixo de ${doc.limiar}%: uma pessoa confirma antes de o documento entrar na conferência.`}
            </p>
            {doc.status === 'revisao' && <a href="#revisao" className="mt-3 inline-block text-sm font-bold text-tinta hover:underline">Confirmar na Revisão humana →</a>}
          </section>

          <section className="rounded-2xl border border-borda p-5">
            <h2 className="text-[0.9375rem] font-bold">Identificação documental</h2>
            <p className="mt-2 text-sm font-semibold">{doc.subtipo_rotulo || 'Não identificado'}</p>
            <p className="mt-1 text-xs text-apoio">
              {doc.subtipo_manual ? 'Corrigido por revisor' :
                doc.subtipo_revisao ? 'Identificação complementar precisa de conferência' :
                'Identificação por regras documentais'}
              {doc.subtipo_pontos != null ? ` · Pontuação heurística ${doc.subtipo_pontos} (não é acurácia)` : ''}
            </p>
            {(doc.subtipo_evidencias || []).length > 0 && (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-apoio">
                {doc.subtipo_evidencias.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
            {podeDecidir && (
              <label className="mt-3 grid gap-1 text-xs font-semibold">
                Corrigir subtipo
                <select value={doc.subtipo || 'nao_identificado'} onChange={(e) => corrigirSubtipo(e.target.value)}
                        className="rounded-xl border border-borda bg-white p-2 text-sm">
                  {Object.entries({
                    nfse: 'NFS-e', danfe: 'DANFE / NF-e', nfce: 'NFC-e', cte: 'CT-e / DACTE',
                    contrato: 'Contrato', aditivo: 'Aditivo', distrato: 'Distrato',
                    boleto: 'Boleto', comprovante_pagamento: 'Comprovante de pagamento',
                    recibo: 'Recibo', nao_identificado: 'Não identificado',
                  }).map(([v, rotulo]) => <option key={v} value={v}>{rotulo}</option>)}
                </select>
              </label>
            )}
          </section>

          <section className="rounded-2xl border border-borda p-5">
            <h2 className="text-[0.9375rem] font-bold">Campos lidos{doc.dados?.provisorio ? ' (provisórios)' : ''}</h2>
            {Object.keys(campos).length === 0 ? (
              <p className="mt-2 text-[0.8125rem] text-apoio">{doc.aviso || 'Este tipo de documento não tem campos para a conferência.'}</p>
            ) : (
              <dl className="mt-2 grid">
                {Object.entries(campos).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 border-b border-borda py-2 text-[0.8125rem] last:border-0">
                    <dt className="text-apoio">{NOMES[k] || k}</dt>
                    <dd className={`text-right font-bold ${k === 'valor' && abertas.some((x) => x.regra === 'VALOR_DIVERGENTE') ? 'text-erro' : ''}`}>{valorCampo(k, v)}</dd>
                  </div>
                ))}
                {nota?.contrato && (
                  <div className="flex justify-between gap-4 py-2 text-[0.8125rem]">
                    <dt className="text-apoio">Contrato conferido</dt>
                    <dd className="text-right font-bold">{nota.contrato.numero}{nota.aditivos?.length ? ` + ${nota.aditivos.length} aditivo(s)` : ''}</dd>
                  </div>
                )}
              </dl>
            )}
          </section>

          <details className="rounded-2xl border border-borda p-5">
            <summary className="cursor-pointer text-[0.9375rem] font-bold">Texto reconhecido{doc.protegidos ? ` · ${doc.protegidos} dado(s) protegido(s)` : ''}</summary>
            <p className="mt-3 max-h-80 overflow-auto text-[0.8125rem] leading-relaxed whitespace-pre-wrap text-apoio">{doc.texto || 'Sem texto.'}</p>
          </details>
        </div>
      </div>
    </div>
  )
}
