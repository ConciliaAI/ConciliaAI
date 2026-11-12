import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'
import { curto, DUVIDA, nomeDocumento, resumoProblema } from '../documentos'

// Fila única, como no Figma: dúvidas da leitura (documentos) e divergências da conferência (notas × contrato).
const SEVERIDADE = { critica: ['Crítica', 'bg-erro-fundo text-erro'], alta: ['Alta', 'bg-ambar-fundo text-ambar-texto'], media: ['Média', 'bg-papel text-apoio'] }

const brl = (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }))
const imagem = (pid, largura = 460) => `/api/paginas/${pid}/imagem?largura=${largura}`
const numeros = (texto = '') => (texto.match(/págs?\. ([\d, ]+) do lote/)?.[1] || '').split(',').map((n) => +n.trim()).filter(Boolean)

function chave(item) {
  return `${item.tipoItem}-${item.id}`
}

// Monta a pergunta de cada item: título, aviso, páginas em destaque, respostas e um rodapé explicando.
function pergunta(item, tipos) {
  if (item.tipoItem === 'divergencia') {
    return {
      titulo: `${item.origem === 'xml' ? 'NFS-e' : 'Nota'} nº ${item.numero} · ${item.nome_prestador || item.cnpj_fmt}`,
      meta: `${brl(item.valor)} · emitida em ${item.data_emissao ? new Date(item.data_emissao + 'T00:00').toLocaleDateString('pt-BR') : '—'}${item.contrato_numero ? ` · contrato ${item.contrato_numero}` : ''}`,
      aviso: [item.titulo, item.mensagem],
      rodape: <>O contrato prevê <b>{item.esperado || '—'}</b>. A nota apresenta <b>{item.encontrado || '—'}</b>.</>,
      respostas: [
        { rotulo: 'Aprovar mesmo assim', acao: { acao: 'aprovar' }, principal: true },
        { rotulo: 'Rejeitar a nota', acao: { acao: 'rejeitar' }, precisaMotivo: true },
      ],
    }
  }
  const pags = item.paginas || []
  const base = {
    titulo: nomeDocumento(item),
    meta: `${pags.length} página${pags.length === 1 ? '' : 's'} · envio #${item.envio_id} · confiança ${item.conf}%`,
  }
  if (item.duvida === 'integridade') {
    const problemas = (item.sinais || []).filter((s) => /^(Página repetida|Documento incompleto|Página escaneada)/.test(s))
    const ns = numeros(problemas[0])
    return {
      ...base,
      aviso: [resumoProblema(problemas[0] || item.motivo), 'Um documento com página repetida ou faltando não deve ser usado para conferir notas.'],
      destaque: ns.length >= 2 ? ns.slice(0, 2) : [item.pag_ini, item.pag_fim],
      legendas: ns.length >= 2 ? ['Cópia A', 'Cópia B'] : ['Primeira página', 'Última página'],
      rodape: 'Se o documento está completo do jeito que veio, aceite. Se não, peça a via completa ao fornecedor.',
      respostas: [
        { rotulo: 'Aceitar o documento', acao: { acao: 'confirmar' }, principal: true },
        { rotulo: 'Pedir nova cópia', acao: { acao: 'pedir' } },
        { rotulo: 'Ler de novo', acao: { acao: 'reprocessar' } },
      ],
    }
  }
  if (item.duvida === 'fronteira' && pags.length > 1) {
    const fraca = +((item.motivo || '').match(/\d+/) || [0])[0]
    const dividir = fraca > item.pag_ini && fraca <= item.pag_fim
    return {
      ...base,
      aviso: [`Estas ${pags.length} páginas são um ${curto(item.tipo).toLowerCase()} só?`, dividir ? `A IA desconfia que um documento novo começa na página ${fraca}.` : 'A IA não tem certeza de onde cada documento começa.'],
      destaque: dividir ? [fraca - 1, fraca] : [item.pag_ini, item.pag_ini + 1],
      legendas: dividir ? ['Página anterior', 'Começa outro aqui?'] : ['Página 1', 'Página 2'],
      rodape: 'Folha ilegível ou em branco no meio de um contrato normalmente continua o mesmo documento.',
      respostas: [
        { rotulo: 'É um documento só', acao: { acao: 'confirmar' }, principal: true },
        ...(dividir ? [{ rotulo: `Começa outro na pág. ${fraca}`, acao: { acao: 'dividir', pagina: fraca } }] : []),
        { rotulo: 'Ler de novo', acao: { acao: 'reprocessar' } },
      ],
    }
  }
  const candidatos = (item.candidatos || []).map((c) => c[0]).filter((t) => t && t !== 'Não identificado')
  if (item.tipo !== 'Não identificado' && !candidatos.includes(item.tipo)) candidatos.unshift(item.tipo)
  return {
    ...base,
    aviso: [DUVIDA.tipo(item), 'A leitura ficou com pouca confiança. Confirme o tipo do documento.'],
    destaque: [item.pag_ini, Math.min(item.pag_ini + 1, item.pag_fim)].filter((n, i, a) => a.indexOf(n) === i),
    legendas: ['Primeira página', 'Segunda página'],
    rodape: 'Sua resposta vira exemplo: a IA acerta mais nos próximos documentos parecidos.',
    respostas: candidatos.slice(0, 3).map((t, i) => ({
      rotulo: i === 0 && t === item.tipo ? `Sim, é ${curto(t).toLowerCase()}` : `É ${curto(t).toLowerCase()}`,
      acao: { acao: 'confirmar', tipo: t }, principal: i === 0,
    })),
    outrosTipos: tipos,
  }
}

function CartaoFila({ item, ativo, aoClicar }) {
  const doc = item.tipoItem === 'documento'
  const [sev, corSev] = SEVERIDADE[item.severidade] || []
  return (
    <button onClick={aoClicar} aria-current={ativo ? 'true' : undefined}
            className={`grid min-h-[6.25rem] w-full content-center gap-1 rounded-2xl border px-4 py-3.5 text-left transition-colors
              ${ativo ? 'border-confere bg-nevoa/60 ring-1 ring-confere' : 'border-borda bg-white hover:border-confere/50'}`}>
      <span className="flex items-center gap-2.5 text-[0.9375rem] font-bold">
        <span className={`size-2 shrink-0 rounded-full ${doc ? (item.duvida === 'integridade' ? 'bg-erro' : 'bg-ambar') : 'bg-erro'}`} />
        <span className="truncate">{doc ? DUVIDA[item.duvida]?.(item) || 'Leitura com dúvida' : item.titulo}</span>
      </span>
      <span className="truncate text-[0.8125rem] text-apoio">
        {doc ? nomeDocumento(item) : `${item.origem === 'xml' ? 'NFS-e' : 'Nota'} nº ${item.numero} · ${item.nome_prestador || item.cnpj_fmt}`}
      </span>
      <span className="flex gap-2">
        {doc
          ? <span className="rounded-full bg-ambar-fundo px-2.5 py-0.5 text-xs font-semibold text-ambar-texto">Confiança {item.conf}%</span>
          : <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${corSev}`}>{sev} · {item.encontrado}</span>}
      </span>
    </button>
  )
}

function Pagina({ pagina, legenda, destaque }) {
  return (
    <figure className={`grid gap-2.5 rounded-2xl p-4 ${destaque ? 'bg-nevoa' : 'bg-papel'}`}>
      <div className="grid h-[18.25rem] place-items-center overflow-hidden rounded-lg">
        {pagina
          ? <img src={imagem(pagina.id)} alt={`Página ${pagina.n} do lote`} className="max-h-full max-w-full rounded-md bg-white shadow-sm" />
          : <span className="text-sm text-suave">Página indisponível</span>}
      </div>
      <figcaption className="flex justify-between gap-2 text-[0.8125rem]">
        <b className="truncate">{legenda}{pagina ? ` · página ${pagina.n} do lote` : ''}</b>
        {pagina?.conf != null && <span className="shrink-0 text-xs text-apoio">confiança {pagina.conf}%</span>}
      </figcaption>
    </figure>
  )
}

function Painel({ item, tipos, podeDecidir, aoDecidir, ocupado }) {
  const [motivo, setMotivo] = useState('')
  const [pedindoMotivo, setPedindoMotivo] = useState(false)
  const [extras, setExtras] = useState(null) // páginas da nota e do contrato (divergência)
  const p = pergunta(item, tipos)

  useEffect(() => {
    setMotivo(''); setPedindoMotivo(false); setExtras(null)
    if (item.tipoItem !== 'divergencia') return
    const ids = [item.nota_doc_id, item.contrato_doc_id]
    Promise.all(ids.map((id) => (id ? api.get(`/api/docs/${id}`).catch(() => null) : null))).then(setExtras)
  }, [item])

  function responder(r) {
    if (r.precisaMotivo && !pedindoMotivo) return setPedindoMotivo(true)
    aoDecidir(item, { ...r.acao, comentario: motivo.trim() })
  }

  // Atalhos 1, 2 e 3 (fora de campos de texto).
  useEffect(() => {
    function tecla(e) {
      if (!podeDecidir || ocupado || /input|textarea|select/i.test(e.target.tagName)) return
      const r = p.respostas[+e.key - 1]
      if (r) { e.preventDefault(); responder(r) }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  })

  const todas = [...(item.vizinhas || []).filter((v) => v.n < item.pag_ini), ...(item.paginas || []), ...(item.vizinhas || []).filter((v) => v.n > item.pag_fim)]
  const porN = Object.fromEntries((item.paginas || []).concat(item.vizinhas || []).map((pg) => [pg.n, pg]))
  const grandes = item.tipoItem === 'divergencia'
    ? [[extras?.[0]?.paginas?.[0], 'Nota fiscal'], [extras?.[1]?.paginas?.[0], 'Contrato']]
    : (p.destaque || []).map((n, i) => [porN[n], p.legendas[i]])

  return (
    <section className="rounded-2xl border border-borda p-4 sm:p-6">
      <h2 className="truncate text-xl font-bold">{p.titulo}</h2>
      <p className="mt-0.5 text-[0.8125rem] text-apoio">{p.meta}</p>

      <div className="mt-4 flex items-center gap-3 rounded-xl bg-ambar-fundo px-4 py-2.5 text-ambar-texto">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-ambar/25 text-base font-bold" aria-hidden="true">!</span>
        <span className="grid min-w-0">
          <b className="text-sm">{p.aviso[0]}</b>
          <span className="text-[0.8125rem]">{p.aviso[1]}</span>
        </span>
      </div>

      {item.tipoItem === 'documento' && todas.length > 1 && (
        <div className="mt-5 flex gap-2 overflow-x-auto pb-1" aria-label="Páginas do documento">
          {todas.slice(0, 12).map((pg) => {
            const fora = pg.n < item.pag_ini || pg.n > item.pag_fim
            const marcada = p.destaque?.includes(pg.n)
            return (
              <span key={pg.id} className="grid shrink-0 justify-items-center gap-1">
                <img src={imagem(pg.id, 120)} alt="" loading="lazy"
                     className={`h-[4.25rem] w-[3.25rem] rounded-md border bg-white object-cover object-top
                       ${marcada ? 'border-2 border-ambar' : 'border-borda'} ${fora ? 'opacity-40' : ''}`} />
                <span className={`text-[0.6875rem] ${marcada ? 'font-bold text-ambar-texto' : 'text-suave'}`}>pág. {pg.n}</span>
              </span>
            )
          })}
        </div>
      )}

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {grandes.map(([pg, legenda], i) => <Pagina key={i} pagina={pg} legenda={legenda} destaque={i === 1} />)}
      </div>

      <p className="mt-4 text-[0.8125rem] text-apoio">{p.rodape}</p>

      {pedindoMotivo && (
        <label className="mt-3 grid gap-1.5 text-sm font-semibold">Motivo da rejeição (vai para o relatório)
          <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2} autoFocus
                    className="rounded-xl border border-borda px-3 py-2 font-normal outline-none focus:border-confere focus:ring-2 focus:ring-confere/25" />
        </label>
      )}

      {!podeDecidir && <p className="mt-3 rounded-xl bg-ambar-fundo px-4 py-3 text-sm text-ambar-texto">Você entrou como operador. Só revisor ou administrador pode responder.</p>}

      <div className={`mt-4 flex flex-wrap items-center gap-3 ${podeDecidir ? '' : 'pointer-events-none opacity-50'}`}>
        {p.respostas.map((r, i) => (
          <button key={r.rotulo} onClick={() => responder(r)} disabled={ocupado || (r.precisaMotivo && pedindoMotivo && motivo.trim().length < 3)}
                  className={`h-[2.875rem] rounded-full px-6 text-sm font-bold transition-colors disabled:opacity-50
                    ${r.principal ? 'bg-confere text-white hover:bg-[#2559e0]'
                      : r.precisaMotivo ? 'border-2 border-erro text-erro hover:bg-erro-fundo'
                      : i === 1 ? 'border-2 border-confere text-tinta hover:bg-nevoa' : 'bg-papel text-noite hover:bg-borda'}`}>
            {r.precisaMotivo && pedindoMotivo ? 'Confirmar rejeição' : r.rotulo}
          </button>
        ))}
        {item.tipoItem === 'documento' && (
          <select value="" onChange={(e) => { const v = e.target.value; if (v) aoDecidir(item, JSON.parse(v)) }} aria-label="Outra resposta"
                  className="h-[2.875rem] rounded-full border border-borda bg-white px-4 text-sm font-semibold text-apoio">
            <option value="">Outra resposta…</option>
            {item.vizinhas?.some((v) => v.n < item.pag_ini) && <option value={JSON.stringify({ acao: 'juntar' })}>Juntar com o documento anterior</option>}
            <option value={JSON.stringify({ acao: 'pedir' })}>Pedir nova cópia</option>
            <option value={JSON.stringify({ acao: 'reprocessar' })}>Ler de novo</option>
            {(p.outrosTipos || tipos).map((t) => <option key={t} value={JSON.stringify({ acao: 'confirmar', tipo: t })}>É {t}</option>)}
          </select>
        )}
      </div>
      <p className="mt-3 text-right text-xs text-suave">Atalhos: {p.respostas.map((_, i) => i + 1).join(', ')}</p>
    </section>
  )
}

export default function Revisao({ ws, perfil, aoMudar }) {
  const [dados, setDados] = useState(null)
  const [selecionado, setSelecionado] = useState(null)
  const [aviso, setAviso] = useState(null)
  const [ocupado, setOcupado] = useState(false)
  const podeDecidir = perfil === 'revisor' || perfil === 'admin'

  const carregar = useCallback(async () => {
    try {
      const [pend, div, visao] = await Promise.all([
        api.get(`/api/ws/${ws}/pendencias`), api.get(`/api/ws/${ws}/divergencias?status=aberta`), api.get(`/api/ws/${ws}/visao`),
      ])
      const fila = [
        ...pend.pendencias.map((d) => ({ ...d, tipoItem: 'documento' })),
        ...div.divergencias.map((d) => ({ ...d, tipoItem: 'divergencia' })),
      ]
      setDados({ fila, tipos: pend.tipos, decididos: visao.decididos + (div.contagem.aprovada || 0) + (div.contagem.rejeitada || 0) })
      return fila
    } catch (e) {
      setAviso({ texto: e.message, erro: true })
      return []
    }
  }, [ws])

  useEffect(() => { if (ws) carregar() }, [ws, carregar])

  async function decidir(item, acao) {
    setOcupado(true)
    const indice = dados.fila.findIndex((x) => chave(x) === chave(item))
    try {
      const url = item.tipoItem === 'divergencia' ? `/api/divergencias/${item.id}/decisao` : `/api/docs/${item.id}/decisao`
      const r = await api.post(url, acao)
      setAviso({ texto: r.msg || 'Resposta registrada.' })
      const fila = await carregar()
      // Vai para o próximo da fila (o que ficou na mesma posição).
      const prox = fila[Math.min(indice, fila.length - 1)]
      setSelecionado(prox ? chave(prox) : null)
      aoMudar?.()
    } catch (err) {
      setAviso({ texto: err.message, erro: true })
    } finally {
      setOcupado(false)
    }
  }

  if (!dados) return <p className="text-apoio">Carregando…</p>
  const { fila, tipos } = dados
  const atual = fila.find((x) => chave(x) === selecionado) || fila[0]
  const contar = (f) => fila.filter(f).length
  const resumo = [
    ['Páginas repetidas ou faltando', contar((x) => x.duvida === 'integridade')],
    ['Onde começa o documento', contar((x) => x.duvida === 'fronteira')],
    ['Leitura com dúvida', contar((x) => x.tipoItem === 'documento' && !['integridade', 'fronteira'].includes(x.duvida))],
    ['Nota diferente do contrato', contar((x) => x.tipoItem === 'divergencia')],
  ]

  return (
    <div className="grid grid-cols-1">
      <h1 className="text-[2.125rem] leading-[1.25] font-bold">Revisão humana</h1>
      <p className="mt-0.5 text-[0.9375rem] text-apoio">
        {fila.length ? `A IA ficou em dúvida em ${fila.length} ${fila.length === 1 ? 'item' : 'itens'}. Sua resposta vira exemplo para os próximos.` : 'Nada para revisar agora.'}
      </p>

      {aviso && (
        <p className={`mt-4 flex items-start justify-between gap-4 rounded-xl px-4 py-3 text-sm ${aviso.erro ? 'bg-erro-fundo text-erro' : 'bg-nevoa text-tinta'}`} role="status">
          {aviso.texto}
          <button onClick={() => setAviso(null)} aria-label="Fechar aviso"><Icone nome="fechar" className="size-4" /></button>
        </p>
      )}

      {/* Figma: fila 352 à esquerda, pergunta 680 à direita, espaço 24. */}
      <div className="mt-5 grid grid-cols-1 items-start gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
        <div className="grid content-start gap-3">
          {fila.map((x) => <CartaoFila key={chave(x)} item={x} ativo={atual && chave(x) === chave(atual)} aoClicar={() => setSelecionado(chave(x))} />)}

          <div className="mt-2 rounded-2xl bg-noite p-6 text-white">
            <p className="text-sm text-white/70">Já resolvidas</p>
            <p className="font-titulo text-[2.125rem] font-bold">{dados.decididos}</p>
            <p className="text-[0.8125rem] text-white/70">As respostas ensinam a IA a separar melhor os próximos documentos da sua conta.</p>
            <p className="mt-5 text-[0.6875rem] font-bold tracking-[0.08em] text-[#8CB3FF]">NA FILA AGORA</p>
            <div className="mt-2 grid gap-2.5">
              {resumo.map(([rotulo, n]) => (
                <p key={rotulo} className="flex h-[2.125rem] items-center justify-between rounded-lg bg-white/8 px-3.5 text-[0.8125rem]">
                  {rotulo}<b>{n}</b>
                </p>
              ))}
            </div>
          </div>
        </div>

        {atual ? (
          <Painel key={chave(atual)} item={atual} tipos={tipos} podeDecidir={podeDecidir} aoDecidir={decidir} ocupado={ocupado} />
        ) : (
          <section className="grid min-h-[20rem] place-items-center rounded-2xl border border-dashed border-borda p-8 text-center">
            <div>
              <p className="text-lg font-bold">Tudo revisado</p>
              <p className="mt-1 text-sm text-apoio">Quando a IA tiver dúvida num documento ou uma nota não bater com o contrato, aparece aqui.</p>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
