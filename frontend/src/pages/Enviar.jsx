import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// Envio ainda em andamento (a tela se atualiza sozinha enquanto houver um).
const ATIVOS = ['recebendo', 'fila', 'processando', 'pausado', 'falhou']
const SITUACAO = {
  recebendo: ['Recebendo', 'bg-nevoa text-tinta'],
  fila: ['Na fila', 'bg-nevoa text-tinta'],
  processando: ['Lendo', 'bg-nevoa text-tinta'],
  pausado: ['Pausado', 'bg-ambar-fundo text-ambar-texto'],
  falhou: ['Tentando de novo', 'bg-ambar-fundo text-ambar-texto'],
  concluido: ['Concluído', 'bg-nevoa text-tinta'],
  recusado: ['Recusado', 'bg-erro-fundo text-erro'],
  cancelado: ['Cancelado', 'bg-papel text-apoio'],
}
const FORMATOS = ['XML da NFS-e', 'PDF', 'TIFF', 'JPG ou PNG', 'ZIP']
const ACEITOS = '.xml,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.zip,.bmp,.webp'
const PASSOS = [
  ['Separa os documentos', 'onde cada um começa e termina'],
  ['Classifica e faz o OCR', 'texto pesquisável em toda página'],
  ['Confere nota × contrato', 'valor, vigência, duplicidade'],
  ['Pergunta quando tem dúvida', 'vai para a revisão humana'],
]

function Selo({ status }) {
  const [rotulo, cor] = SITUACAO[status] || [status, 'bg-papel text-apoio']
  return <span className={`rounded-full px-2.5 py-1 text-xs font-bold whitespace-nowrap ${cor}`}>{rotulo}</span>
}

// "hoje, 10h04", "ontem, 9h12" ou "02/10, 15h21"
function quando(texto) {
  if (!texto) return ''
  const d = new Date(texto.replace(' ', 'T'))
  const hora = `${d.getHours()}h${String(d.getMinutes()).padStart(2, '0')}`
  const dias = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5)
  if (dias === 0) return `hoje, ${hora}`
  if (dias === 1) return `ontem, ${hora}`
  return `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${hora}`
}

function plural(n, um, varios) {
  return `${n} ${n === 1 ? um : varios}`
}

function resultado(e) {
  if (e.status === 'recusado') return e.erro || 'Nenhum arquivo legível'
  if (e.status === 'cancelado') return `Parado na página ${e.feitas} de ${e.total}`
  const partes = []
  if (e.documentos) partes.push(plural(e.documentos, 'documento', 'documentos'))
  if (e.duvidas) partes.push(plural(e.duvidas, 'dúvida', 'dúvidas'))
  if (e.notas_xml) partes.push(plural(e.notas_xml, 'nota em XML', 'notas em XML'))
  return partes.join(' · ') || '—'
}

// Miniaturas das páginas (Figma): ✓ nas lidas, traço escuro no alto de quem começa um documento,
// contorno azul na página sendo lida agora e cinza nas que ainda vão ser lidas.
function Miniaturas({ paginas }) {
  const atual = paginas.findIndex((p) => p.status === 'pendente')
  const fim = atual === -1 ? paginas.length : atual
  const janela = paginas.slice(Math.max(0, fim - 12), Math.max(0, fim - 12) + 16)
  return (
    <div className="flex gap-2 overflow-hidden" aria-hidden="true">
      {janela.map((p) => {
        const lida = p.status === 'feita'
        const agora = paginas.indexOf(p) === atual
        if (!lida && !agora) return <span key={p.id} className="h-[2.875rem] w-10 shrink-0 rounded-md bg-papel" />
        return (
          <span key={p.id} title={`Página ${p.n}`}
                className={`relative grid h-[2.875rem] w-10 shrink-0 content-center gap-[3px] rounded-md border bg-white px-2
                  ${agora ? 'border-2 border-confere' : 'border-borda'} ${lida && p.inicio ? 'border-t-[3px] border-t-noite' : ''}`}>
            {[0, 1, 2, 3].map((i) => <span key={i} className={`h-[2px] rounded bg-borda ${i === 3 ? 'w-2/3' : ''}`} />)}
            {lida && (
              <span className="absolute -right-1 -bottom-1 grid size-3.5 place-items-center rounded-full bg-confere text-[0.5rem] font-bold text-white">✓</span>
            )}
            {p.status === 'erro' && <span className="absolute -right-1 -bottom-1 size-3.5 rounded-full bg-erro" />}
          </span>
        )
      })}
    </div>
  )
}

function falta(segundos) {
  if (segundos == null) return 'calculando o tempo…'
  if (segundos < 60) return 'falta menos de 1 min'
  return `faltam cerca de ${Math.round(segundos / 60)} min`
}

function EnvioAtivo({ envio, detalhe, restante, aoAgir }) {
  const [confirmar, setConfirmar] = useState(false)
  const paginas = detalhe?.paginas || []
  const feitas = envio.feitas || 0
  const total = envio.total || 0
  const pct = total ? Math.round((feitas / total) * 100) : 0
  const encontrados = paginas.filter((p) => p.status === 'feita' && p.inicio).length

  const lendo = ['fila', 'processando'].includes(envio.status)
  return (
    <section className="mt-6 rounded-2xl border border-borda px-4 pt-4 pb-5 sm:px-6">
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-nevoa text-confere"><Icone nome="contratos" className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-bold">{envio.nome}</p>
          <p className="text-[0.8125rem] text-apoio">
            {plural(total, 'página', 'páginas')} · enviado {quando(envio.criado_em)}{lendo ? ' · lendo agora' : ''}
          </p>
        </div>
        <Selo status={envio.status} />
        {lendo && (
          <button onClick={() => aoAgir(envio.id, 'pausar')}
                  className="h-10 w-[8.125rem] rounded-full border-2 border-confere text-sm font-bold text-tinta hover:bg-nevoa">Pausar</button>
        )}
        {['pausado', 'falhou'].includes(envio.status) && (
          <button onClick={() => aoAgir(envio.id, 'retomar')}
                  className="h-10 w-[8.125rem] rounded-full bg-confere text-sm font-bold text-white hover:bg-[#2559e0]">Retomar</button>
        )}
        {envio.status !== 'recebendo' && (
          <button onClick={() => { if (confirmar) aoAgir(envio.id, 'cancelar'); else { setConfirmar(true); setTimeout(() => setConfirmar(false), 4000) } }}
                  className={`h-10 w-[8rem] rounded-full text-sm font-bold ${confirmar ? 'bg-erro text-white' : 'bg-papel text-noite hover:bg-borda'}`}>
            {confirmar ? 'Confirmar?' : 'Cancelar'}
          </button>
        )}
      </div>
      <div className="mt-4 h-1.5 rounded-full bg-papel" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-confere transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2.5 flex flex-wrap justify-between gap-2 text-[0.8125rem]">
        <p className="font-bold">{feitas} de {total} páginas lidas · {plural(encontrados, 'documento encontrado', 'documentos encontrados')}</p>
        <p className="text-apoio">{envio.status === 'pausado' ? 'pausado: nada se perde' : envio.status === 'falhou' ? 'retomando da última página salva' : falta(restante)}</p>
      </div>
      {paginas.length > 0 && <div className="mt-3"><Miniaturas paginas={paginas} /></div>}
    </section>
  )
}

export default function Enviar({ ws, aoMudar }) {
  const [envios, setEnvios] = useState(null)
  const [detalhe, setDetalhe] = useState(null)
  const [arrastando, setArrastando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [aviso, setAviso] = useState(null) // { texto, erro }
  const [restante, setRestante] = useState(null) // segundos até terminar
  const entrada = useRef(null)
  const amostra = useRef(null) // primeira medição do envio ativo: { id, t, f }

  const carregar = useCallback(async () => {
    try {
      const lista = await api.get(`/api/ws/${ws}/envios`)
      setEnvios(lista)
      const ativo = lista.find((e) => ATIVOS.includes(e.status))
      // Tempo restante pelo ritmo medido desde que a tela abriu (páginas por segundo).
      const agora = Date.now()
      if (ativo && amostra.current?.id !== ativo.id) amostra.current = { id: ativo.id, t: agora, f: ativo.feitas }
      const passou = ativo ? (agora - amostra.current.t) / 1000 : 0
      const porSeg = ativo && passou > 4 && ativo.feitas > amostra.current.f ? (ativo.feitas - amostra.current.f) / passou : null
      setRestante(ativo?.status === 'processando' && porSeg ? (ativo.total - ativo.feitas) / porSeg : null)
      setDetalhe(ativo ? await api.get(`/api/envios/${ativo.id}`) : null)
    } catch (e) {
      setAviso({ texto: e.message, erro: true })
    }
  }, [ws])

  useEffect(() => { if (ws) carregar() }, [ws, carregar])
  const ativo = envios?.find((e) => ATIVOS.includes(e.status))
  useEffect(() => {
    if (!ativo) return
    const t = setTimeout(() => { carregar(); aoMudar?.() }, 1500)
    return () => clearTimeout(t)
  }, [envios, ativo, carregar, aoMudar])

  async function enviar(arquivos) {
    if (!arquivos?.length) return
    const fd = new FormData()
    for (const a of arquivos) fd.append('arquivos', a)
    setEnviando(true)
    setAviso(null)
    try {
      const e = await api.enviar(`/api/ws/${ws}/envios`, fd)
      setAviso(e.status === 'recusado'
        ? { texto: e.erro || 'Nenhum arquivo legível.', erro: true }
        : { texto: `Recebido: ${plural(e.total || 0, 'página', 'páginas')}${e.notas_xml ? ` e ${plural(e.notas_xml, 'nota', 'notas')} em XML` : ''}. A leitura já começou.` })
      await carregar()
      aoMudar?.()
    } catch (err) {
      setAviso({ texto: err.message, erro: true })
    } finally {
      setEnviando(false)
    }
  }

  async function agir(eid, acao) {
    try {
      await api.post(`/api/envios/${eid}/${acao}`)
      setAviso({ texto: { pausar: 'Pausado. Nada se perde: a leitura continua de onde parou.', retomar: 'Retomando da próxima página.', cancelar: 'Envio cancelado.' }[acao] })
      await carregar()
      aoMudar?.()
    } catch (err) {
      setAviso({ texto: err.message, erro: true })
    }
  }

  const anteriores = (envios || []).filter((e) => !ATIVOS.includes(e.status)).slice(0, 8)
  return (
    <div className="grid grid-cols-1">
      <h1 className="text-[2.125rem] leading-[1.25] font-bold">Enviar documentos</h1>
      <p className="mt-0.5 text-[0.9375rem] text-apoio">Lotes de XML, PDF, TIFF, fotos ou ZIP, até 300 MB por envio.</p>

      {/* Figma: área de arrastar 700x300 + "Como o lote é lido" 340x300, espaço 16. */}
      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_21.25rem]">
        <label
          onDragOver={(e) => { e.preventDefault(); setArrastando(true) }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => { e.preventDefault(); setArrastando(false); enviar(e.dataTransfer.files) }}
          className={`flex min-h-[18.75rem] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors
            ${arrastando ? 'border-confere bg-nevoa' : 'border-confere/60 bg-white hover:bg-nevoa/40'}`}>
          <span className="grid size-[4.5rem] place-items-center rounded-full bg-nevoa text-confere"><Icone nome="enviar" className="size-6" /></span>
          <span className="mt-4 font-titulo text-[1.375rem] font-bold">{enviando ? 'Enviando…' : arrastando ? 'Pode soltar' : 'Arraste o lote para cá'}</span>
          <span className="mt-1 text-sm text-apoio">Do jeito que saiu do scanner: misturado, fora de ordem e num arquivo só.</span>
          <span className="mt-5 grid h-[2.875rem] w-[11.25rem] place-items-center rounded-full bg-confere text-sm font-bold text-white">Escolher arquivos</span>
          <span className="mt-4 flex flex-wrap justify-center gap-2">
            {FORMATOS.map((f) => <span key={f} className="rounded-full border border-borda px-3 py-1 text-xs text-apoio">{f}</span>)}
          </span>
          <input ref={entrada} type="file" multiple accept={ACEITOS} className="sr-only" disabled={enviando}
                 onChange={(e) => { enviar(e.target.files); e.target.value = '' }} />
        </label>

        <aside className="rounded-2xl bg-noite p-6 text-white">
          <h2 className="text-lg font-bold">Como o lote é lido</h2>
          <ol className="mt-5 grid gap-5">
            {PASSOS.map(([titulo, detalhe], i) => (
              <li key={titulo} className="flex gap-3">
                <span className="grid size-[1.625rem] shrink-0 place-items-center rounded-full bg-confere text-[0.8125rem] font-bold">{i + 1}</span>
                <span className="grid">
                  <span className="text-sm font-bold">{titulo}</span>
                  <span className="text-[0.78125rem] text-white/65">{detalhe}</span>
                </span>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {aviso && (
        <p className={`mt-4 flex items-start justify-between gap-4 rounded-xl px-4 py-3 text-sm ${aviso.erro ? 'bg-erro-fundo text-erro' : 'bg-nevoa text-tinta'}`} role="status">
          {aviso.texto}
          <button onClick={() => setAviso(null)} aria-label="Fechar aviso"><Icone nome="fechar" className="size-4" /></button>
        </p>
      )}

      {ativo && <EnvioAtivo envio={ativo} detalhe={detalhe?.envio?.id === ativo.id ? detalhe : null} restante={restante} aoAgir={agir} />}

      <h2 className="mt-6 text-lg font-bold">Envios anteriores</h2>
      {envios === null ? <p className="mt-3 text-sm text-apoio">Carregando…</p> : anteriores.length === 0 ? (
        <p className="mt-3 text-sm text-apoio">Nenhum envio ainda. Arraste o primeiro lote acima.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          {/* Colunas do Figma: arquivo 308, páginas 120, resultado 230, quando 170, situação. */}
          <table className="w-full min-w-[42rem] table-fixed text-[0.8125rem]">
            <colgroup><col className="w-[30%]" /><col className="w-[11%]" /><col className="w-[28%]" /><col className="w-[16%]" /><col className="w-[15%]" /></colgroup>
            <thead>
              <tr className="h-9 text-left text-[0.6875rem] tracking-[0.04em] text-suave uppercase">
                <th className="pr-4 pl-6 font-bold">Arquivo</th><th className="pr-4 font-bold">Páginas</th>
                <th className="pr-4 font-bold">Resultado</th><th className="pr-4 font-bold">Quando</th><th className="font-bold">Situação</th>
              </tr>
            </thead>
            <tbody>
              {anteriores.map((e) => (
                <tr key={e.id} className="h-10 border-t border-borda">
                  <td className="truncate pr-4 pl-6 text-[0.84375rem] font-bold" title={e.nome}>{e.nome}</td>
                  <td className="pr-4 text-apoio tabular-nums">{e.total ? e.total : e.notas_xml ? `${e.notas_xml} XML` : '—'}</td>
                  <td className="truncate pr-4 text-apoio" title={resultado(e)}>{resultado(e)}</td>
                  <td className="pr-4 text-apoio">{quando(e.criado_em)}</td>
                  <td><Selo status={e.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
