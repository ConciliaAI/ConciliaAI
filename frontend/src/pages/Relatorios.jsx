import { useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// Tela Relatórios, como no Figma: notas conferidas no mês, divergências por regra e as planilhas para baixar.
// Os números vêm de /api/ws/{ws}/relatorios; as planilhas, de /api/ws/{ws}/relatorio.csv?tipo=...

// Nomes curtos das regras, como no layout.
const REGRA_CURTA = {
  VALOR_DIVERGENTE: 'Valor acima do contrato',
  FORA_VIGENCIA: 'Fora da vigência',
  NOTA_DUPLICADA: 'Nota duplicada',
  SERVICO_DIVERGENTE: 'Serviço diferente',
  TOMADOR_DIVERGENTE: 'Outro tomador',
  SEM_CONTRATO: 'Sem contrato',
}
const ORDEM = Object.keys(REGRA_CURTA) // a ordem do Figma

// Sem a planilha de fornecedores (decisão da reunião): no lugar dela entram os documentos lidos.
const PLANILHAS = [
  ['divergencias', 'Divergências', 'Cada diferença encontrada, com regra, gravidade e decisão'],
  ['notas', 'Notas fiscais', 'Todas as notas lidas, com valores e contrato vinculado'],
  ['documentos', 'Documentos lidos', 'Tipo, páginas, confiança e decisão sobre a leitura'],
  ['trilha', 'Trilha de decisões', 'Quem aprovou, rejeitou ou excluiu, quando e por quê'],
  ['avisos', 'Avisos aos fornecedores', 'Mensagens geradas e para quem foram enviadas'],
  ['acessos', 'Acessos a dados protegidos', 'Quem viu o original anonimizado e o motivo informado'],
]

const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
function nomeMes(mes, maiuscula = false) {
  if (!mes) return 'Sem notas'
  const [a, m] = mes.split('-')
  const nome = `${MESES[+m - 1]} de ${a}`
  return maiuscula ? nome[0].toUpperCase() + nome.slice(1) : nome
}

// Rosca com uma fatia por situação (raio 59, traço 22: o desenho de 140 px do Figma).
function Rosca({ fatias, total }) {
  const raio = 59
  const volta = 2 * Math.PI * raio
  // Cada fatia começa onde as anteriores terminam.
  const arcos = fatias.filter((f) => f.valor > 0).map((f, i, lista) => ({
    ...f,
    tamanho: (f.valor / total) * volta,
    inicio: lista.slice(0, i).reduce((soma, g) => soma + (g.valor / total) * volta, 0),
  }))
  return (
    <div className="relative size-[8.75rem] shrink-0">
      <svg viewBox="0 0 140 140" className="size-full -rotate-90">
        <circle cx="70" cy="70" r={raio} fill="none" stroke="#F2F4F8" strokeWidth="22" />
        {total > 0 && arcos.map((a) => (
          <circle key={a.rotulo} cx="70" cy="70" r={raio} fill="none" stroke={a.cor} strokeWidth="22"
                  strokeDasharray={`${a.tamanho} ${volta - a.tamanho}`} strokeDashoffset={-a.inicio} />
        ))}
      </svg>
      <div className="absolute inset-0 grid place-content-center text-center">
        <span className="font-titulo text-[1.875rem] leading-none font-extrabold">{total}</span>
        <span className="text-xs text-apoio">{total === 1 ? 'nota' : 'notas'}</span>
      </div>
    </div>
  )
}

export default function Relatorios({ ws, cliente }) {
  const [dados, setDados] = useState(null)
  const [mes, setMes] = useState('')
  const [erro, setErro] = useState('')

  useEffect(() => {
    if (!ws) return
    api.get(`/api/ws/${ws}/relatorios${mes ? `?mes=${mes}` : ''}`)
      .then((r) => { setDados(r); setErro('') })
      .catch((e) => setErro(e.message))
  }, [ws, mes])

  if (erro) return <p className="rounded-2xl bg-erro-fundo p-6 text-erro">{erro}</p>
  if (!dados) return <p className="text-apoio">Carregando…</p>

  const n = dados.notas
  const fatias = [
    { rotulo: 'Sem divergência', valor: n.sem_divergencia, cor: '#2F6BFF' },
    { rotulo: 'Com divergência', valor: n.com_divergencia, cor: '#C93434' },
    { rotulo: 'Aguardando contrato', valor: n.aguardando_contrato, cor: '#F5B700' },
  ]
  const maior = Math.max(1, ...dados.regras.map((r) => r.total))

  return (
    <div className="grid gap-[1.375rem]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[2.125rem] font-extrabold">Relatórios</h1>
          <p className="text-[0.9375rem] text-apoio">
            Tudo vira planilha. {nomeMes(dados.mes, true)}{cliente ? ` · ${cliente}` : ''}
          </p>
        </div>
        <label className="relative mt-2.5 block w-[13rem]">
          <span className="sr-only">Mês</span>
          <select value={dados.mes} onChange={(e) => setMes(e.target.value)} disabled={!dados.meses.length}
                  className="h-[2.875rem] w-full cursor-pointer appearance-none rounded-xl border border-borda bg-white pr-10 pl-6 text-sm font-bold outline-none focus:border-confere disabled:cursor-default">
            {dados.meses.length ? dados.meses.map((m) => <option key={m} value={m}>{nomeMes(m, true)}</option>)
              : <option value="">Sem notas ainda</option>}
          </select>
          <Icone nome="abaixo" className="pointer-events-none absolute top-1/2 right-4 size-4 -translate-y-1/2" />
        </label>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,420fr)_minmax(0,620fr)]">
        <section className="grid content-start gap-6 rounded-[1.25rem] border border-[#E3E7EF] p-6 pt-[1.1875rem]">
          <h2 className="text-[1.0625rem] font-extrabold">Notas conferidas no mês</h2>
          <div className="flex flex-wrap items-center gap-x-[3.75rem] gap-y-4 pl-7">
            <Rosca fatias={fatias} total={n.total} />
            <ul className="grid min-w-[9rem] gap-[1.125rem] text-[0.8125rem]">
              {fatias.map((f) => (
                <li key={f.rotulo} className="flex items-center gap-2">
                  <span className="size-2 rounded-full" style={{ background: f.cor }} />
                  <span className="flex-1 text-apoio">{f.rotulo}</span>
                  <b className="pl-6">{f.valor}</b>
                </li>
              ))}
            </ul>
          </div>
          {n.total === 0 && <p className="text-sm text-apoio">Nenhuma nota neste mês. Envie notas e contratos para começar a conferência.</p>}
        </section>

        <section className="grid content-start gap-[1.375rem] rounded-[1.25rem] border border-[#E3E7EF] p-6 pt-[1.1875rem]">
          <h2 className="text-[1.0625rem] font-extrabold">Divergências por regra</h2>
          <ul className="grid gap-7 text-[0.8125rem]">
            {[...dados.regras].sort((a, b) => ORDEM.indexOf(a.regra) - ORDEM.indexOf(b.regra)).map((r) => (
              <li key={r.regra} className="grid grid-cols-[minmax(7rem,12rem)_minmax(0,1fr)_1.5rem] items-center gap-x-4">
                <span className="text-apoio">{REGRA_CURTA[r.regra] || r.titulo}</span>
                <span className="h-4 overflow-hidden rounded-full bg-[#F2F4F8]">
                  <span className="block h-full rounded-full"
                        style={{ width: `${(r.total / maior) * 100}%`, background: r.total === maior ? '#C93434' : '#E57373' }} />
                </span>
                <b className="text-right">{r.total}</b>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="grid gap-4">
        <h2 className="text-lg font-extrabold">Planilhas para baixar</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {PLANILHAS.map(([tipo, titulo, texto]) => (
            <article key={tipo} className="grid grid-cols-[2.75rem_minmax(0,1fr)] gap-x-4 rounded-[1.25rem] border border-[#E3E7EF] p-5 pb-4">
              <span className="row-span-2 grid size-11 place-items-center rounded-xl bg-nevoa text-confere">
                <Icone nome="planilha" className="size-5" />
              </span>
              <div className="pt-0.5">
                <h3 className="font-sans text-[0.9375rem] font-bold">{titulo}</h3>
                <p className="mt-1 text-[0.78125rem] text-apoio">{texto}</p>
              </div>
              <a href={`/api/ws/${ws}/relatorio.csv?tipo=${tipo}`} download
                 className="col-start-2 mt-1 flex h-[1.875rem] items-center gap-2 justify-self-end rounded-lg bg-[#F2F4F8] px-3.5 text-[0.78125rem] font-bold hover:bg-nevoa">
                <Icone nome="baixar" className="size-4" />Baixar CSV
              </a>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
