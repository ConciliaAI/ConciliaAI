import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// Tela Contratos: a referência da conferência. Cada nota é comparada com o contrato do prestador,
// somando os aditivos vigentes na data da nota. Os dados vêm de /api/ws/{ws}/contratos.
// O Figma não tem esta tela: segue o mesmo desenho do dashboard (números no topo e tabela que rola por dentro).

const brl = (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }))
const cnpj = (v) => {
  const d = (v || '').replace(/\D/g, '')
  return d.length === 14 ? d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : v || '—'
}
const data = (iso) => (iso ? new Date(`${iso}T00:00`).toLocaleDateString('pt-BR') : '—')

// Situação da vigência: vencido, vence em até 30 dias, vigente ou sem data lida.
function vigencia(c, hoje) {
  if (!c.vigencia_fim) return ['Sem data', 'bg-papel text-apoio']
  const dias = Math.round((new Date(`${c.vigencia_fim}T00:00`) - hoje) / 86_400_000)
  if (dias < 0) return ['Vencido', 'bg-erro-fundo text-erro']
  if (dias <= 30) return [`Vence em ${dias} dia${dias === 1 ? '' : 's'}`, 'bg-ambar-fundo text-ambar-texto']
  if (c.vigencia_inicio && new Date(`${c.vigencia_inicio}T00:00`) > hoje) return ['Ainda não começou', 'bg-papel text-apoio']
  return ['Vigente', 'bg-ok-fundo text-ok']
}

function Numero({ titulo, valor, detalhe, cor = '' }) {
  return (
    <div className="grid content-start gap-1 rounded-2xl border border-borda px-5 py-4">
      <p className="text-sm text-apoio">{titulo}</p>
      <p className={`font-titulo text-[1.75rem] leading-tight font-bold tabular-nums ${cor}`}>{valor}</p>
      {detalhe && <p className="text-xs text-apoio">{detalhe}</p>}
    </div>
  )
}

export default function Contratos({ ws }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [busca, setBusca] = useState('')
  const [aberto, setAberto] = useState(null)
  const [hoje] = useState(() => new Date(new Date().toDateString()))

  useEffect(() => {
    if (!ws) return
    api.get(`/api/ws/${ws}/contratos`).then(setDados).catch((e) => setErro(e.message))
  }, [ws])

  if (erro) return <p className="rounded-2xl bg-erro-fundo p-6 text-erro">{erro}</p>
  if (!dados) return <p className="text-apoio">Carregando…</p>

  const contratos = dados.contratos
  const soltos = dados.aditivos_sem_contrato
  const termo = busca.trim().toLowerCase()
  const visiveis = termo
    ? contratos.filter((c) => [c.numero, c.nome_prestador, c.cnpj_fmt, c.objeto].some((v) => (v || '').toLowerCase().includes(termo)))
    : contratos
  const mensal = contratos.reduce((s, c) => s + (c.valor_mensal || 0), 0)
  const faturado = contratos.reduce((s, c) => s + (c.faturado || 0), 0)
  const abertas = contratos.reduce((s, c) => s + (c.abertas || 0), 0)
  const aVencer = contratos.filter((c) => ['Vencido', 'Vence'].some((p) => vigencia(c, hoje)[0].startsWith(p))).length

  return (
    <div className="grid grid-cols-1">
      <h1 className="text-[2.125rem] leading-[1.25] font-bold">Contratos</h1>
      <p className="mt-0.5 text-[0.9375rem] text-apoio">
        A referência da conferência: objeto, valor mensal, vigência e aditivos, lidos dos PDFs. Cada nota é comparada com o contrato do seu prestador.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Numero titulo="Contratos lidos" valor={contratos.length} detalhe={soltos.length ? `${soltos.length} aditivo(s) sem contrato` : 'todos os aditivos ligados'} />
        <Numero titulo="Valor mensal somado" valor={brl(mensal)} detalhe="sem contar os aditivos" />
        <Numero titulo="Faturado nas notas" valor={brl(faturado)} detalhe={`${contratos.reduce((s, c) => s + c.notas, 0)} notas ligadas a contratos`} />
        <Numero titulo="Vencidos ou a vencer" valor={aVencer} detalhe={abertas ? `${abertas} divergência(s) aberta(s)` : 'nenhuma divergência aberta'}
                cor={aVencer ? 'text-ambar-texto' : 'text-ok'} />
      </div>

      <section className="mt-7 min-w-0 rounded-2xl border border-borda px-6 pt-4 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold">Todos os contratos</h2>
            <span className="text-xs text-apoio">{visiveis.length} resultado(s)</span>
          </div>
          <label className="flex h-9 w-full max-w-[20rem] items-center gap-2 rounded-full bg-papel px-4 text-sm">
            <Icone nome="busca" className="size-4 text-suave" />
            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Número, prestador, CNPJ ou objeto"
                   aria-label="Buscar contrato" className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-suave" />
          </label>
        </div>

        {contratos.length === 0 ? (
          <div className="grid justify-items-start gap-3 py-6">
            <p className="text-sm text-apoio">Nenhum contrato ainda. Envie os contratos em PDF (pode ser digitalizado). Sem contrato, toda nota do prestador vira a divergência “Fornecedor sem contrato”.</p>
            <a href="#enviar" className="flex h-10 items-center gap-2 rounded-full bg-confere px-5 text-sm font-bold text-white hover:bg-[#2559e0]">
              <Icone nome="mais" className="size-4" />Enviar documentos
            </a>
          </div>
        ) : visiveis.length === 0 ? (
          <p className="py-6 text-sm text-apoio">Nenhum contrato encontrado para “{busca}”.</p>
        ) : (
          <div className="mt-3 max-h-[28rem] overflow-auto overscroll-contain [scrollbar-width:thin]">
            <table className="w-full min-w-[56rem] table-fixed text-[0.8125rem]">
              <colgroup>
                <col className="w-[24%]" /><col className="w-[22%]" /><col className="w-[12%]" /><col className="w-[15%]" />
                <col className="w-[9%]" /><col className="w-[11%]" /><col className="w-[7%]" />
              </colgroup>
              <thead>
                <tr className="sticky top-0 z-10 h-9 bg-white text-left text-[0.6875rem] tracking-[0.04em] whitespace-nowrap text-suave uppercase">
                  <th className="pr-4 font-bold">Contrato</th><th className="pr-4 font-bold">Objeto</th>
                  <th className="pr-4 font-bold">Valor mensal</th><th className="pr-4 font-bold">Vigência</th>
                  <th className="pr-4 font-bold">Notas</th><th className="pr-4 font-bold">Faturado</th>
                  <th><span className="sr-only">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map((c) => {
                  const [situacao, cor] = vigencia(c, hoje)
                  const expandido = aberto === c.id
                  return (
                    <Fragment key={c.id}>
                      <tr className="h-14 border-t border-borda align-middle">
                        <td className="pr-4">
                          <button type="button" onClick={() => setAberto(expandido ? null : c.id)} aria-expanded={expandido}
                                  className="flex w-full min-w-0 items-center gap-3 text-left">
                            <span className="grid size-7 shrink-0 place-items-center rounded-lg border border-borda text-confere">
                              <Icone nome="abaixo" className={`size-4 transition-transform ${expandido ? '' : '-rotate-90'}`} />
                            </span>
                            <span className="grid min-w-0">
                              <b className="truncate text-[0.84375rem]">{c.numero || 'Sem número'}</b>
                              <span className="truncate text-xs text-apoio">{c.nome_prestador || 'Prestador não identificado'} · {c.cnpj_fmt}</span>
                            </span>
                          </button>
                        </td>
                        <td className="pr-4 text-apoio"><span className="line-clamp-2">{c.objeto || '—'}</span></td>
                        <td className="pr-4 font-bold tabular-nums">{brl(c.valor_mensal)}</td>
                        <td className="pr-4">
                          <span className={`rounded-full px-2.5 py-1 text-xs font-bold whitespace-nowrap ${cor}`}>{situacao}</span>
                          <span className="mt-1 block text-xs text-apoio tabular-nums">{data(c.vigencia_inicio)} a {data(c.vigencia_fim)}</span>
                        </td>
                        <td className="pr-4 tabular-nums">
                          {c.notas}
                          {c.abertas > 0 && <a href="#revisao" className="ml-2 rounded-full bg-erro-fundo px-2 py-0.5 text-xs font-bold text-erro hover:underline">{c.abertas} aberta{c.abertas === 1 ? '' : 's'}</a>}
                        </td>
                        <td className="pr-4 tabular-nums">{brl(c.faturado)}</td>
                        <td className="text-right">
                          {c.doc_id && (
                            <a href={`#documento-${c.doc_id}`} title="Abrir o documento do contrato"
                               className="inline-flex h-8 items-center gap-1 rounded-full border border-borda px-3 text-xs font-bold hover:bg-papel">
                              <Icone nome="olho" className="size-4" />Ver
                            </a>
                          )}
                        </td>
                      </tr>
                      {expandido && (
                        <tr className="bg-papel/70">
                          <td colSpan={7} className="px-4 py-4">
                            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                              <div className="grid content-start gap-1.5 text-[0.8125rem]">
                                <p className="text-xs font-bold tracking-[0.04em] text-suave uppercase">Lido do contrato</p>
                                <p><span className="text-apoio">Objeto:</span> {c.objeto || '—'}</p>
                                <p><span className="text-apoio">Valor total:</span> {brl(c.valor_total)}</p>
                                <p><span className="text-apoio">Tomador:</span> {cnpj(c.cnpj_tomador)}</p>
                                {c.doc_id && (
                                  <a href={`/api/docs/${c.doc_id}/pdf`} className="mt-1 inline-flex w-fit items-center gap-1.5 font-bold text-tinta hover:underline">
                                    <Icone nome="baixar" className="size-4" />Baixar PDF pesquisável
                                  </a>
                                )}
                              </div>
                              <div className="grid content-start gap-2 text-[0.8125rem]">
                                <p className="text-xs font-bold tracking-[0.04em] text-suave uppercase">Aditivos ({c.aditivos.length})</p>
                                {c.aditivos.length === 0 && <p className="text-apoio">Nenhum aditivo encontrado para este contrato.</p>}
                                {c.aditivos.map((a) => (
                                  <div key={a.id} className="flex items-start justify-between gap-3 rounded-xl border border-borda bg-white px-3 py-2">
                                    <span className="grid">
                                      <b>{a.numero || 'Aditivo'}</b>
                                      <span className="text-xs text-apoio tabular-nums">{data(a.vigencia_inicio)} a {data(a.vigencia_fim)}</span>
                                    </span>
                                    <span className="font-bold whitespace-nowrap text-ok tabular-nums">+{brl(a.valor_adicional)}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {soltos.length > 0 && (
        <section className="mt-5 grid gap-3 rounded-2xl border border-ambar/50 bg-ambar-fundo/40 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold">Aditivos sem contrato encontrado</h2>
            <p className="text-sm text-apoio">Foram lidos, mas o contrato a que se referem não está aqui. Envie o contrato para que o acréscimo entre na conferência.</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {soltos.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-3 rounded-xl border border-borda bg-white px-3 py-2 text-[0.8125rem]">
                <span className="grid min-w-0">
                  <b className="truncate">{a.numero || 'Aditivo'}</b>
                  <span className="truncate text-xs text-apoio">Contrato {a.contrato_ref || '?'}</span>
                </span>
                <span className="font-bold whitespace-nowrap tabular-nums">+{brl(a.valor_adicional)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
