import { useState } from 'react'
import Icone from './Icone'

const PERFIS = { admin: 'Administrador', revisor: 'Revisor', operador: 'Operador' }

function iniciais(nome = '') {
  return nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('') || '?'
}

// Medidas do Figma: barra de 72 de altura; busca 420x48 a 16 da borda; sino 48; avatar 44.
export default function BarraTopo({ usuario, alertas = 0, aoBuscar, aoAbrirMenu }) {
  const [termo, setTermo] = useState('')
  const segundaLinha = PERFIS[usuario?.perfil] === usuario?.nome ? `@${usuario?.usuario}` : PERFIS[usuario?.perfil] || usuario?.perfil
  return (
    <header className="flex h-[4.5rem] shrink-0 items-center gap-3 rounded-[1.75rem] bg-white pr-5 pl-4">
      <button onClick={aoAbrirMenu} className="rounded-xl p-2 text-apoio hover:bg-papel lg:hidden" aria-label="Abrir menu">
        <Icone nome="menu" />
      </button>
      <form className="relative min-w-0 flex-1 sm:max-w-[26.25rem]"
            onSubmit={(e) => { e.preventDefault(); if (termo.trim()) aoBuscar(termo.trim()) }}>
        <Icone nome="busca" className="pointer-events-none absolute top-1/2 left-[1.125rem] size-4 -translate-y-1/2 text-suave" />
        <input value={termo} onChange={(e) => setTermo(e.target.value)} type="search"
               placeholder="Buscar no texto de todos os documentos" aria-label="Buscar nos documentos"
               className="h-12 w-full rounded-full bg-papel pr-4 pl-[2.875rem] text-sm outline-none placeholder:text-suave focus:ring-2 focus:ring-confere/40" />
      </form>
      <div className="ml-auto flex items-center gap-2.5">
        <button className="relative grid size-12 place-items-center rounded-full border border-borda text-noite hover:bg-papel"
                aria-label={alertas > 0 ? `Notificações: ${alertas} pendente(s)` : 'Notificações'}>
          <Icone nome="sino" className="size-5" />
          {alertas > 0 && <span className="absolute top-3 right-3.5 size-2 rounded-full bg-erro ring-2 ring-white" />}
        </button>
        <div className="flex items-center gap-2.5">
          <span className="grid size-11 place-items-center rounded-full bg-confere text-[0.8125rem] font-bold text-white">{iniciais(usuario?.nome)}</span>
          <div className="hidden leading-tight sm:block">
            <p className="text-sm font-bold">{usuario?.nome}</p>
            <p className="text-xs text-suave">{segundaLinha}</p>
          </div>
        </div>
      </div>
    </header>
  )
}
