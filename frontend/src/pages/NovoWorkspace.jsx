import { useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// Um workspace por cliente da empresa: notas, contratos, regras e documentos ficam separados por cliente.
export default function NovoWorkspace({ primeiro, podeCriar, aoCriar }) {
  const [nome, setNome] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [setor, setSetor] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function criar(e) {
    e.preventDefault()
    if (nome.trim().length < 2) return setErro('Informe o nome do cliente.')
    setEnviando(true)
    setErro('')
    try {
      const w = await api.post('/api/clientes', { nome, cnpj, setor })
      await aoCriar(w.id)
    } catch (err) {
      setErro(err.message)
      setEnviando(false)
    }
  }

  const campo = 'w-full rounded-xl border border-borda bg-white px-4 py-3 text-[0.9375rem] outline-none focus:border-confere focus:ring-2 focus:ring-confere/25'
  return (
    <div className="grid max-w-[40rem] gap-6">
      <div>
        <h1 className="text-[2.125rem] leading-[1.25] font-bold">{primeiro ? 'Crie o primeiro workspace' : 'Novo workspace'}</h1>
        <p className="mt-0.5 text-[0.9375rem] text-apoio">
          Cada cliente da sua empresa tem um workspace: notas, contratos, regras e documentos ficam separados, e você troca de cliente na barra do topo.
        </p>
      </div>
      {!podeCriar ? (
        <p className="rounded-2xl bg-papel p-6 text-apoio">Só o administrador da conta cria workspaces. Peça para ele criar o do seu cliente.</p>
      ) : (
        <form onSubmit={criar} className="grid gap-4 rounded-2xl border border-borda p-6">
          <label className="grid gap-1.5 text-sm font-medium">Nome do cliente
            <input className={campo} value={nome} onChange={(e) => setNome(e.target.value)} autoFocus placeholder="Ex.: Padaria Pão Quente Ltda." />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium"><span>CNPJ <span className="font-normal text-suave">(opcional)</span></span>
              <input className={campo} value={cnpj} onChange={(e) => setCnpj(e.target.value)} inputMode="numeric" placeholder="00.000.000/0000-00" />
            </label>
            <label className="grid gap-1.5 text-sm font-medium"><span>Setor <span className="font-normal text-suave">(opcional)</span></span>
              <input className={campo} value={setor} onChange={(e) => setSetor(e.target.value)} placeholder="Ex.: Comércio" />
            </label>
          </div>
          {erro && <p className="rounded-lg bg-erro-fundo px-3 py-2 text-sm text-erro" role="alert">{erro}</p>}
          <button disabled={enviando}
                  className="flex h-12 w-fit items-center gap-2 rounded-full bg-confere px-6 text-sm font-bold text-white hover:bg-[#2559e0] disabled:opacity-60">
            <Icone nome="mais" className="size-4" />{enviando ? 'Criando…' : 'Criar workspace'}
          </button>
        </form>
      )}
    </div>
  )
}
