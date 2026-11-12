import { Fragment, useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// O servidor devolve o trecho com [[termo]] e dados protegidos como ⟦CPF⟧: aqui viram destaque e etiqueta.
function Trecho({ texto }) {
  const partes = texto.split(/(\[\[[^\]]+\]\]|⟦[^⟧]+⟧)/g)
  return partes.map((p, i) => {
    if (p.startsWith('[[')) return <mark key={i} className="rounded bg-ambar-fundo px-0.5 text-noite">{p.slice(2, -2)}</mark>
    if (p.startsWith('⟦')) return <span key={i} className="rounded bg-nevoa px-1 text-xs font-semibold text-tinta">{p.slice(1, -1)}</span>
    return <Fragment key={i}>{p}</Fragment>
  })
}

export default function Busca({ ws, termo }) {
  const [resultado, setResultado] = useState(null)
  useEffect(() => {
    if (!ws || !termo) return
    setResultado(null)
    api.get(`/api/ws/${ws}/busca?q=${encodeURIComponent(termo)}`).then(setResultado).catch(() => setResultado([]))
  }, [ws, termo])

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-[2.125rem] font-extrabold">Busca</h1>
        <p className="text-sm text-apoio">{termo ? <>Resultados para “{termo}”</> : 'Digite um termo na barra de busca.'}</p>
      </div>
      {termo && !resultado && <p className="text-apoio">Buscando…</p>}
      {resultado?.length === 0 && <p className="rounded-2xl bg-papel p-6 text-apoio">Nada encontrado. Tente um fornecedor, um número de contrato ou um serviço.</p>}
      <div className="grid gap-3">
        {resultado?.map((d) => (
          <article key={d.id} className="grid gap-2 rounded-2xl border border-borda p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid size-9 place-items-center rounded-xl bg-nevoa text-confere"><Icone nome="arquivo" className="size-[1.125rem]" /></span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{d.tipo}</p>
                <p className="text-xs text-suave">{d.empresa || 'Empresa não identificada'} · envio #{d.envio_id} · pág. {d.pag_ini}–{d.pag_fim}</p>
              </div>
              <a href={`#documento-${d.id}`} className="flex items-center gap-1.5 rounded-xl bg-confere px-3 py-2 text-sm font-semibold text-white hover:bg-[#2559e0]">Abrir</a>
              <a href={`/api/docs/${d.id}/pdf`} className="flex items-center gap-1.5 rounded-xl border border-borda px-3 py-2 text-sm font-semibold hover:bg-papel">
                <Icone nome="baixar" className="size-4" />PDF
              </a>
            </div>
            <p className="text-sm leading-relaxed text-apoio"><Trecho texto={d.trecho} /></p>
          </article>
        ))}
      </div>
    </div>
  )
}
