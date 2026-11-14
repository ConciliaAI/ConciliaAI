import { LIMITE_DOCUMENTOS } from '../api'
import { GERAL, MENU } from '../menu'
import Icone from './Icone'
import Logo from './Logo'

// Medidas do Figma: itens de 216x46 a cada 52px, ícone 18 a 18px da borda, texto 15 (o ativo em negrito).
const ITEM = 'flex h-[2.875rem] items-center gap-3.5 rounded-xl px-[1.125rem] text-[0.9375rem] transition-colors [@media(max-height:760px)]:h-10'

function Item({ item, ativo, contagem, aoClicar }) {
  return (
    <a href={`#${item.id}`} onClick={aoClicar} aria-current={ativo ? 'page' : undefined}
       className={`${ITEM} ${ativo ? 'bg-confere font-bold text-white' : 'text-white/75 hover:bg-white/8 hover:text-white'}`}>
      <Icone nome={item.icone} className="size-[1.125rem] shrink-0" />
      <span className="truncate">{item.rotulo}</span>
      {contagem > 0 && (
        <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-ambar px-1.5 text-xs font-bold text-[#3D2C00]">{contagem}</span>
      )}
    </a>
  )
}

const ROTULO = 'px-2 pb-2.5 text-[0.6875rem] font-bold tracking-[0.08em] text-[#8CB3FF]'

export default function MenuLateral({ rota, contagens, totalDocumentos, limite = LIMITE_DOCUMENTOS, aoSair, aoNavegar }) {
  // Documentos da conta inteira (todos os workspaces), contra o limite do plano.
  const usados = totalDocumentos ?? 0
  const pct = Math.min(100, (usados / limite) * 100)
  return (
    <aside className="flex h-full min-h-full w-[15.5rem] flex-col rounded-[1.75rem] bg-noite p-4 pt-[1.625rem] text-white">
      <div className="px-2 pb-[2.375rem] [@media(max-height:760px)]:pb-5"><Logo claro /></div>

      <p className={ROTULO}>MENU</p>
      <nav className="grid gap-1.5">
        {MENU.map((item) => (
          <Item key={item.id} item={item} ativo={rota === item.id} contagem={contagens?.[item.contador]} aoClicar={aoNavegar} />
        ))}
      </nav>

      <p className={`${ROTULO} pt-7 [@media(max-height:760px)]:pt-4`}>GERAL</p>
      <nav className="grid gap-1.5">
        {GERAL.map((item) => <Item key={item.id} item={item} ativo={rota === item.id} aoClicar={aoNavegar} />)}
        <button onClick={aoSair} className={`${ITEM} text-left text-white/75 hover:bg-white/8 hover:text-white`}>
          <Icone nome="sair" className="size-[1.125rem]" />Sair
        </button>
      </nav>

      <div className="mt-auto grid shrink-0 gap-3 rounded-2xl bg-white/6 p-4">
        <div>
          <p className="text-sm font-bold">Plano Essencial</p>
          <p className="text-xs text-white/60">
            {usados.toLocaleString('pt-BR')} de {limite.toLocaleString('pt-BR')} documentos
          </p>
        </div>
        <div className="h-1.5 rounded-full bg-white/15" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-confere" style={{ width: `${Math.max(pct, usados ? 2 : 0)}%` }} />
        </div>
        <button className="h-10 rounded-xl bg-confere text-sm font-bold hover:bg-[#2559e0]">Fazer upgrade</button>
      </div>
    </aside>
  )
}
