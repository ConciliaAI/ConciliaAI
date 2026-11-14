import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import BarraTopo from './components/BarraTopo'
import MenuLateral from './components/MenuLateral'
import { MENU } from './menu'
import Busca from './pages/Busca'
import Contratos from './pages/Contratos'
import Dashboard from './pages/Dashboard'
import EmMigracao from './pages/EmMigracao'
import Enviar from './pages/Enviar'
import Relatorios from './pages/Relatorios'
import Fiscais from './pages/Fiscais'
import Revisao from './pages/Revisao'
import Documento from './pages/Documento'
import Login from './pages/Login'

function rotaAtual() {
  return window.location.hash.replace('#', '').split('?')[0] || 'documentos'
}

export default function App() {
  const [estado, setEstado] = useState(null) // null = carregando
  const [rota, setRota] = useState(rotaAtual)
  const [contagens, setContagens] = useState(null)
  const [totalDocs, setTotalDocs] = useState(null)
  const [menuAberto, setMenuAberto] = useState(false)
  const [busca, setBusca] = useState('')

  const carregar = useCallback(async () => {
    try {
      setEstado(await api.get('/api/estado'))
    } catch {
      setEstado({ usuario: null, erro: true })
    }
  }, [])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => {
    const mudou = () => { setRota(rotaAtual()); setMenuAberto(false) }
    window.addEventListener('hashchange', mudou)
    return () => window.removeEventListener('hashchange', mudou)
  }, [])

  // Sem workspaces (decisão da reunião): a conta usa o primeiro espaço que a API devolve.
  const ws = estado?.clientes?.[0]?.id

  const atualizarContagens = useCallback(async () => {
    if (!ws) return
    try {
      const [c, v] = await Promise.all([api.get(`/api/ws/${ws}/contagens`), api.get(`/api/ws/${ws}/visao`)])
      // Revisão humana = dúvidas da leitura + divergências abertas (a mesma fila da tela).
      setContagens({ ...c, revisao: (c.pendencias || 0) + (c.divergencias || 0) })
      setTotalDocs(v.documentos)
    } catch { /* o menu continua sem os números */ }
  }, [ws])
  useEffect(() => { atualizarContagens() }, [atualizarContagens, rota])

  async function sair() {
    await api.post('/api/sair').catch(() => {})
    setEstado({ usuario: null })
  }

  if (!estado) return <div className="grid min-h-screen place-items-center text-apoio">Carregando…</div>
  if (estado.erro) {
    return (
      <div className="grid min-h-screen place-items-center px-4 text-center">
        <div className="grid gap-2">
          <h1 className="text-2xl font-extrabold">Não foi possível falar com o servidor</h1>
          <p className="text-apoio">Confira se a plataforma está rodando (uvicorn app.main:app --port 8000) e recarregue.</p>
        </div>
      </div>
    )
  }
  if (!estado.usuario) return <Login aoEntrar={carregar} />

  let pagina
  if (rota === 'documentos') pagina = <Dashboard ws={ws} perfil={estado.usuario.perfil} aoMudar={atualizarContagens} />
  else if (rota.startsWith('documento-')) pagina = <Documento key={rota} id={+rota.split('-')[1]} perfil={estado.usuario.perfil} aoMudar={atualizarContagens} />
  else if (rota === 'revisao') pagina = <Revisao ws={ws} perfil={estado.usuario.perfil} aoMudar={atualizarContagens} />
  else if (rota === 'enviar') pagina = <Enviar ws={ws} aoMudar={atualizarContagens} />
  else if (rota === 'busca') pagina = <Busca ws={ws} termo={busca} />
  else if (rota === 'contratos') pagina = <Contratos ws={ws} />
  else if (rota === 'relatorios') pagina = <Relatorios ws={ws} cliente={estado.clientes?.[0]?.nome} />
  else if (rota === 'fiscais') pagina = <Fiscais key="lista-fiscais" ws={ws} />
  else if (rota.startsWith('fiscal-')) pagina = <Fiscais key={rota} ws={ws} id={+rota.split('-')[1]} />
  else {
    const item = MENU.find((m) => m.id === rota)
    pagina = <EmMigracao titulo={item?.rotulo || (rota === 'config' ? 'Configurações' : 'Ajuda')} />
  }

  const menu = (
    <MenuLateral rota={rota.startsWith('documento-') ? 'documentos' : rota} contagens={contagens} totalDocumentos={totalDocs} aoSair={sair}
                 aoNavegar={() => setMenuAberto(false)} />
  )
  return (
    // Medidas do Figma (frame de 1440): margem 24, menu 248, espaço 24, barra do topo 72, espaço 20, painel com 32 de respiro.
    <div className="flex min-h-screen gap-6 p-3 sm:p-6">
      {/* Menu estático: rola junto com a página e ocupa a altura toda dela (o plano fica no fim). */}
      <div className="hidden min-h-[calc(100vh-3rem)] w-[15.5rem] shrink-0 lg:block">{menu}</div>
      {menuAberto && (
        <div className="fixed inset-0 z-40 bg-noite/40 p-3 lg:hidden" onClick={() => setMenuAberto(false)}>
          <div className="h-full w-fit rounded-[1.75rem] bg-noite" onClick={(e) => e.stopPropagation()}>{menu}</div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-5">
        <BarraTopo usuario={estado.usuario} alertas={(contagens?.pendencias || 0) + (contagens?.divergencias || 0)} aoAbrirMenu={() => setMenuAberto(true)}
                   aoBuscar={(t) => { setBusca(t); window.location.hash = 'busca' }} />
        <main className="flex-1 rounded-[1.75rem] bg-white px-4 py-6 sm:px-8 sm:pt-[1.875rem] sm:pb-6">{pagina}</main>
      </div>
    </div>
  )
}
