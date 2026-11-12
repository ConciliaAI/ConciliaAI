import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import BlocoScanner from '../components/BlocoScanner'
import CapturaDocumento from '../components/CapturaDocumento'
import Icone from '../components/Icone'
import { curto, DUVIDA, nomeDocumento, pasta } from '../documentos'

const SITUACAO = {
  confirmado: ['Pronto', 'bg-nevoa text-tinta'],
  revisao: ['Revisão', 'bg-ambar-fundo text-ambar-texto'],
  aguardando: ['Aguardando', 'bg-papel text-apoio'],
}

const FILTROS = [['', 'Filtrar'], ['confirmado', 'Prontos'], ['revisao', 'Em revisão'], ['aguardando', 'Aguardando']]

function corConfianca(c) {
  if (c >= 90) return 'text-noite'
  if (c >= 75) return 'text-apoio'
  return 'text-ambar-texto'
}

// Card de número (Figma: 252x140, respiro 20, título 15, número 46, detalhe 13).
function Indicador({ titulo, valor, detalhe, destaque, href, cor }) {
  return (
    <a href={href} className={`flex h-[8.75rem] flex-col rounded-2xl px-5 pt-[1.125rem] pb-4 transition-shadow hover:shadow-md
        ${destaque ? 'bg-confere text-white' : 'border border-borda bg-white'}`}>
      <div className="flex items-start justify-between gap-2">
        <p className={`pt-0.5 text-[0.9375rem] ${destaque ? 'text-white/85' : 'text-apoio'}`}>{titulo}</p>
        <span className={`grid size-8 shrink-0 place-items-center rounded-full border ${destaque ? 'border-white/60' : 'border-borda text-noite'}`}>
          <Icone nome="seta" className="size-4" />
        </span>
      </div>
      <p className="mt-1 font-titulo text-[2.875rem] leading-none font-bold tabular-nums">{valor ?? '–'}</p>
      <p className={`mt-auto truncate text-[0.8125rem] ${destaque ? 'text-white/85' : cor || 'text-tinta'}`}>{detalhe}</p>
    </a>
  )
}

// Pasta do Figma (252x124 com a aba): aba no alto à esquerda, com a borda direita inclinada.
function Pasta({ tipo, quantidade, destaque }) {
  const cor = destaque ? 'bg-confere' : 'bg-nevoa'
  return (
    <div className="relative h-[7.75rem] pt-[1.125rem]">
      <span className={`absolute top-0 left-0 h-[1.375rem] w-[46%] rounded-tl-xl ${cor} [clip-path:polygon(0_0,84%_0,100%_100%,0_100%)]`} />
      <div className={`relative flex h-full flex-col rounded-2xl rounded-tl-none px-5 pt-5 ${cor} ${destaque ? 'text-white' : ''}`}>
        <div className="flex items-start justify-between">
          <p className={`text-[0.6875rem] font-bold tracking-[0.06em] ${destaque ? 'text-white/80' : 'text-apoio'}`}>PASTA</p>
          <Icone nome="contratos" className={`-mt-1 size-6 ${destaque ? '' : 'text-confere'}`} />
        </div>
        <p className="mt-1 truncate font-titulo text-lg font-bold">{tipo}</p>
        <p className={`text-[0.8125rem] ${destaque ? 'text-white/80' : 'text-apoio'}`}>{quantidade} documento{quantidade === 1 ? '' : 's'}</p>
      </div>
    </div>
  )
}

function quando(texto) {
  if (!texto) return ''
  const d = new Date(texto.replace(' ', 'T'))
  const hoje = new Date()
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }).replace(':', 'h')
  return d.toDateString() === hoje.toDateString() ? `enviado hoje às ${hora}` : `enviado em ${d.toLocaleDateString('pt-BR')}`
}

export default function Dashboard({ ws, perfil, aoMudar }) {
  // Excluir é de revisor ou administrador (a API recusa o operador).
  const podeExcluir = perfil === 'revisor' || perfil === 'admin'
  const [confirmando, setConfirmando] = useState(null)
  const [excluindo, setExcluindo] = useState(null)
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [scannerAberto, setScannerAberto] = useState(false)
  const [filtro, setFiltro] = useState('')

  const carregar = useCallback(async () => {
    try {
      const [visao, resumo, documentos, pend] = await Promise.all([
        api.get(`/api/ws/${ws}/visao`), api.get(`/api/ws/${ws}/resumo`),
        api.get(`/api/ws/${ws}/documentos`), api.get(`/api/ws/${ws}/pendencias`),
      ])
      setDados({ visao, resumo, documentos, pendencias: pend.pendencias })
      setErro('')
    } catch (e) {
      setErro(e.message)
    }
  }, [ws])

  useEffect(() => { if (ws) carregar() }, [ws, carregar])
  // Enquanto houver envio sendo lido, atualiza a tela sozinha.
  useEffect(() => {
    if (!dados?.visao?.ativos?.length) return
    const t = setTimeout(() => { carregar(); aoMudar?.() }, 3000)
    return () => clearTimeout(t)
  }, [dados, carregar, aoMudar])

  async function enviarArquivos(arquivos) {
    const fd = new FormData()
    for (const a of arquivos) fd.append('arquivos', a)
    setEnviando(true)
    try {
      const e = await api.enviar(`/api/ws/${ws}/envios`, fd)
      setAviso(e.status === 'recusado' ? e.erro : `Recebido: ${e.total || 0} página(s)${e.notas_xml ? ` e ${e.notas_xml} nota(s) em XML` : ''}. A leitura já começou.`)
      await carregar()
      aoMudar?.()
    } catch (err) {
      setAviso(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function excluir(d) {
    if (confirmando !== d.id) {
      setConfirmando(d.id)
      setTimeout(() => setConfirmando((atual) => (atual === d.id ? null : atual)), 4000)
      return
    }
    setConfirmando(null)
    setExcluindo(d.id)
    try {
      const r = await api.excluir(`/api/docs/${d.id}`)
      setAviso(r.msg || 'Documento excluído.')
      await carregar()
      aoMudar?.()
    } catch (err) {
      setAviso(err.message)
    } finally {
      setExcluindo(null)
    }
  }

  if (erro) return <p className="rounded-2xl bg-erro-fundo p-6 text-erro">{erro}</p>
  if (!dados) return <p className="text-apoio">Carregando…</p>

  const { visao, resumo, documentos, pendencias } = dados
  const ultimo = visao.recentes?.[0]
  const aguardando = resumo.notas - resumo.conciliadas - resumo.divergentes - resumo.rejeitadas
  const tipos = visao.tipos.filter((t) => t.tipo !== 'Não identificado').slice(0, 4)

  return (
    // Distâncias do Figma: cabeçalho → scanner 21, scanner → números 24, números → pastas 28, pastas → tabela 28.
    <div className="grid grid-cols-1">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 basis-[20rem]">
          <h1 className="text-[2.125rem] leading-[1.25] font-bold">Documentos</h1>
          <p className="mt-0.5 truncate text-[0.9375rem] text-apoio" title={ultimo?.nome}>
            {ultimo ? `Último envio: ${ultimo.nome} · ${ultimo.total || 0} páginas · ${quando(ultimo.criado_em)}` : 'Nenhum envio ainda. Escaneie ou envie o primeiro documento.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-3 pt-0.5">
          <a href={`/api/ws/${ws}/documentos.zip`}
             className="grid h-[3.125rem] place-items-center rounded-full border-2 border-confere px-6 text-sm font-bold text-tinta hover:bg-nevoa">Baixar tudo (ZIP)</a>
          <a href="#enviar" className="flex h-[3.125rem] items-center gap-2 rounded-full bg-confere px-6 text-sm font-bold text-white hover:bg-[#2559e0]">
            <Icone nome="mais" className="size-4" />Enviar documentos
          </a>
        </div>
      </div>

      <div className="mt-5" />
      <BlocoScanner enviando={enviando} aoEnviarArquivos={enviarArquivos}
                    aoEscanear={() => setScannerAberto(true)} />
      {aviso && (
        <p className="mt-3 flex items-start justify-between gap-4 rounded-xl bg-nevoa px-4 py-3 text-sm text-tinta" role="status">
          {aviso}
          <button onClick={() => setAviso('')} aria-label="Fechar aviso"><Icone nome="fechar" className="size-4" /></button>
        </p>
      )}

      <CapturaDocumento
        aberto={scannerAberto}
        aoFechar={() => setScannerAberto(false)}
        aoCapturar={(arquivo) => enviarArquivos([arquivo])}
        enviando={enviando}
      />

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Indicador destaque titulo="Páginas lidas" valor={visao.paginas} detalhe={`${visao.documentos} documentos separados`} href="#documentos" />
        <Indicador titulo="Precisam de você" valor={visao.revisao}
                   detalhe={<span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-ambar" />Revisão humana</span>}
                   cor="text-ambar-texto" href="#revisao" />
        <Indicador titulo="Notas conferidas" valor={resumo.notas} href="#relatorios"
                   detalhe={aguardando > 0 ? `${aguardando} aguardando a leitura dos contratos` : `${resumo.conciliadas} sem divergência`} />
        <Indicador titulo="Divergências" valor={resumo.div_abertas} detalhe={resumo.div_abertas ? 'abertas para decidir' : 'nenhuma aberta'}
                   cor={resumo.div_abertas ? 'text-erro' : 'text-ok'} href="#relatorios" />
      </div>

      {tipos.length > 0 && (
        <section className="mt-7 grid gap-[0.9375rem]">
          <h2 className="text-xl leading-[1.25] font-bold">Pastas por tipo</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {tipos.map((t, i) => <Pasta key={t.tipo} tipo={pasta(t.tipo)} quantidade={t.c} destaque={i === 0} />)}
          </div>
        </section>
      )}

      {/* Figma: tabela 712 + painel 328, espaço 16, os dois com 384 de altura. */}
      <div className="mt-7 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_20.5rem]">
        <section className="min-w-0 rounded-2xl border border-borda px-6 pt-4 pb-3 xl:min-h-[24rem]">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Todos os documentos</h2>
            <label className="relative flex h-8 items-center gap-2 rounded-full bg-papel px-4 text-sm font-bold">
              <Icone nome="filtro" className="size-4" />{FILTROS.find((x) => x[0] === filtro)?.[1] || 'Filtrar'}
              <select value={filtro} onChange={(e) => setFiltro(e.target.value)} aria-label="Filtrar documentos"
                      className="absolute inset-0 cursor-pointer opacity-0">
                {FILTROS.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
              </select>
            </label>
          </div>
          {documentos.length === 0 ? (
            <p className="py-6 text-sm text-apoio">Os documentos aparecem aqui depois do primeiro envio.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              {/* Colunas do Figma (664 de largura): documento 288, tipo 120, páginas 80, confiança 88, status 88. */}
              <table className="w-full min-w-[37.5rem] table-fixed text-[0.8125rem]">
                <colgroup><col className="w-[40%]" /><col className="w-[16%]" /><col className="w-[11%]" /><col className="w-[12.5%]" /><col className="w-[13.5%]" />{podeExcluir && <col className="w-[7%]" />}</colgroup>
                <thead>
                  <tr className="h-9 text-left text-[0.6875rem] tracking-[0.04em] whitespace-nowrap text-suave uppercase">
                    <th className="pr-4 font-bold">Documento</th><th className="pr-4 font-bold">Tipo</th>
                    <th className="pr-4 font-bold">Páginas</th><th className="pr-4 font-bold">Confiança</th><th className="font-bold">Status</th>
                    {podeExcluir && <th><span className="sr-only">Ações</span></th>}
                  </tr>
                </thead>
                <tbody>
                  {documentos.filter((d) => !filtro || d.status === filtro).slice(0, 6).map((d) => {
                    const [rotulo, cor] = SITUACAO[d.status] || [d.status, 'bg-papel text-apoio']
                    return (
                      <tr key={d.id} className={`h-12 border-t border-borda ${d.status === 'revisao' ? 'bg-nevoa/60' : ''}`}>
                        <td className="pr-4">
                          <span className="flex items-center gap-3 text-[0.84375rem] font-bold">
                            <span className="grid size-7 shrink-0 place-items-center rounded-lg border border-borda text-confere"><Icone nome="arquivo" className="size-4" /></span>
                            <a href={`#documento-${d.id}`} className="truncate hover:text-tinta hover:underline" title={`Abrir ${nomeDocumento(d)}`}>{nomeDocumento(d)}</a>
                          </span>
                        </td>
                        <td className="pr-4 whitespace-nowrap text-apoio">{curto(d.tipo)}</td>
                        <td className="pr-4 text-apoio tabular-nums">{d.total_paginas}</td>
                        <td className={`pr-4 font-bold tabular-nums ${corConfianca(d.conf)}`}>{d.conf}%</td>
                        <td><span className={`rounded-full px-2.5 py-1 text-xs font-bold whitespace-nowrap ${cor}`}>{rotulo}</span></td>
                        {podeExcluir && (
                          <td className="text-right">
                            {/* Dois cliques: o primeiro arma, o segundo exclui (sem janela de confirmação do navegador). */}
                            <button onClick={() => excluir(d)} disabled={excluindo === d.id}
                                    aria-label={confirmando === d.id ? `Confirmar exclusão de ${nomeDocumento(d)}` : `Excluir ${nomeDocumento(d)}`}
                                    title={confirmando === d.id ? 'Clique de novo para excluir' : 'Excluir documento'}
                                    className={`inline-flex h-8 items-center justify-center gap-1 rounded-full text-xs font-bold transition-colors disabled:opacity-50
                                      ${confirmando === d.id ? 'bg-erro px-3 text-white' : 'w-8 text-suave hover:bg-erro-fundo hover:text-erro'}`}>
                              {confirmando === d.id ? 'Excluir?' : <Icone nome="lixeira" className="size-4" />}
                            </button>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="flex flex-col gap-3 rounded-2xl bg-noite px-4 pt-4 pb-5 text-white">
          <h2 className="flex h-8 items-center gap-2 text-lg font-bold">Precisam de você
            {pendencias.length > 0 && <span className="rounded-full bg-ambar px-2 text-xs font-bold text-[#3D2C00]">{pendencias.length}</span>}
          </h2>
          {pendencias.length === 0 && <p className="text-sm text-white/65">Nada pendente. A IA não teve dúvida nos últimos envios.</p>}
          {pendencias.slice(0, 3).map((p) => (
            <div key={p.id} className="grid min-h-20 content-center gap-1 rounded-xl bg-white/8 px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <span className={`size-2 shrink-0 rounded-full ${p.duvida === 'integridade' ? 'bg-erro' : 'bg-ambar'}`} />
                  <span className="line-clamp-2">{DUVIDA[p.duvida]?.(p) || p.motivo || 'Leitura com dúvida'}</span>
                </p>
                <a href="#revisao" className="rounded-full bg-confere px-3 py-1 text-xs font-bold hover:bg-[#2559e0]">Revisar</a>
              </div>
              <p className="truncate text-xs text-white/60">{nomeDocumento(p)}</p>
            </div>
          ))}
          {pendencias.length > 0 && (
            <a href="#revisao" className="mt-auto pt-1 text-sm font-bold text-[#8CB3FF] hover:underline">Abrir revisão humana →</a>
          )}
        </aside>
      </div>
    </div>
  )
}
