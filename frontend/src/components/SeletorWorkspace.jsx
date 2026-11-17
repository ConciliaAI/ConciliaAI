import { useEffect, useRef, useState } from 'react'
import Icone from './Icone'

// Seletor da barra do topo (Figma: 236x48, sigla colorida + nome do cliente). Cada workspace é um cliente
// da empresa; a lista mostra só os da conta de quem entrou.
function Sigla({ w, className = 'size-7' }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-full text-[0.625rem] font-bold text-white ${className}`}
          style={{ background: w?.cor || '#2F6BFF' }}>
      {w?.sigla || '?'}
    </span>
  )
}

export default function SeletorWorkspace({ clientes, ws, aoTrocar, podeCriar }) {
  const [aberto, setAberto] = useState(false)
  const caixa = useRef(null)
  const atual = clientes.find((w) => w.id === ws)

  useEffect(() => {
    if (!aberto) return
    const fora = (e) => { if (!caixa.current?.contains(e.target)) setAberto(false) }
    const esc = (e) => { if (e.key === 'Escape') setAberto(false) }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', fora); document.removeEventListener('keydown', esc) }
  }, [aberto])

  return (
    <div ref={caixa} className="relative">
      <button type="button" onClick={() => setAberto(!aberto)} aria-haspopup="listbox" aria-expanded={aberto}
              className="flex h-12 max-w-[14.75rem] items-center gap-2.5 rounded-full border border-borda bg-white pr-3 pl-2.5 hover:bg-papel">
        <Sigla w={atual} />
        <span className="hidden min-w-0 flex-1 truncate text-left text-sm font-bold sm:block">{atual?.nome || 'Escolha o cliente'}</span>
        <Icone nome="abaixo" className={`size-4 shrink-0 transition-transform ${aberto ? 'rotate-180' : ''}`} />
      </button>
      {aberto && (
        <div className="absolute top-14 right-0 z-50 grid w-[18rem] gap-1 rounded-2xl border border-borda bg-white p-2 shadow-[0_18px_40px_rgba(15,30,61,0.16)]">
          <p className="px-2.5 pt-1 pb-1.5 text-[0.6875rem] font-bold tracking-[0.06em] text-suave uppercase">Workspaces (clientes)</p>
          <ul role="listbox" aria-label="Workspaces" className="grid max-h-[18rem] gap-0.5 overflow-y-auto">
            {clientes.map((w) => (
              <li key={w.id}>
                <button type="button" role="option" aria-selected={w.id === ws}
                        onClick={() => { aoTrocar(w.id); setAberto(false) }}
                        className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm hover:bg-papel ${w.id === ws ? 'bg-nevoa font-bold' : ''}`}>
                  <Sigla w={w} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{w.nome}</span>
                    {w.setor && <span className="block truncate text-xs font-normal text-suave">{w.setor}</span>}
                  </span>
                  {w.id === ws && <Icone nome="check" className="size-4 text-confere" />}
                </button>
              </li>
            ))}
          </ul>
          {podeCriar && (
            <a href="#novo-workspace" onClick={() => setAberto(false)}
               className="mt-1 flex items-center gap-2 rounded-xl border-t border-borda px-2.5 pt-2.5 pb-1.5 text-sm font-bold text-tinta hover:underline">
              <Icone nome="mais" className="size-4" />Novo workspace
            </a>
          )}
        </div>
      )}
    </div>
  )
}
