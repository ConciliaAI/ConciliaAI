import { useState } from 'react'
import { api } from '../api'
import Logo from '../components/Logo'

// Entrar ou criar a conta da empresa (escritório de BPO, contabilidade...). A conta nasce sem workspaces:
// depois de entrar, a empresa cria um workspace para cada cliente dela.
export default function Login({ aoEntrar, cadastroAberto = true }) {
  const [modo, setModo] = useState('entrar') // 'entrar' | 'criar'
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  const criando = modo === 'criar'

  async function entrar(e) {
    e.preventDefault()
    if (!usuario || !senha) return setErro('Preencha usuário e senha.')
    if (criando && (!empresa.trim() || !nome.trim())) return setErro('Preencha o nome da empresa e o seu nome.')
    if (criando && senha.length < 8) return setErro('A senha precisa ter pelo menos 8 caracteres.')
    setEnviando(true)
    setErro('')
    try {
      if (criando) await api.post('/api/contas', { empresa, nome, usuario, senha })
      else await api.post('/api/login', { usuario, senha })
      await aoEntrar()
    } catch (err) {
      setErro(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const campo = 'w-full rounded-xl border border-borda bg-white px-4 py-3 text-[0.9375rem] outline-none focus:border-confere focus:ring-2 focus:ring-confere/25'
  return (
    <div className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,46%)_1fr]">
      <main className="flex flex-col items-center justify-center px-4 py-12">
        <form onSubmit={entrar} className="grid w-full max-w-[21.25rem] gap-5">
          <div className="grid justify-items-center gap-6 text-center">
            <Logo />
            <div className="grid gap-1.5">
              <h1 className="text-[2rem] font-extrabold">{criando ? 'Criar conta' : 'Bem-vindo de volta'}</h1>
              <p className="text-sm text-apoio">
                {criando ? 'Uma conta para a sua empresa. Depois você cria um workspace para cada cliente.' : 'Entre para conferir seus documentos.'}
              </p>
            </div>
          </div>
          {criando && (
            <>
              <label className="grid gap-1.5 text-sm font-medium">Nome da empresa
                <input className={campo} value={empresa} onChange={(e) => setEmpresa(e.target.value)} autoComplete="organization" autoFocus
                       placeholder="Ex.: Escritório Contábil Silva" />
              </label>
              <label className="grid gap-1.5 text-sm font-medium">Seu nome
                <input className={campo} value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="name" />
              </label>
            </>
          )}
          <label className="grid gap-1.5 text-sm font-medium">Usuário
            <input className={campo} value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoFocus={!criando}
                   placeholder={criando ? 'Ex.: ana.silva' : undefined} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Senha
            <input className={campo} type="password" value={senha} onChange={(e) => setSenha(e.target.value)}
                   autoComplete={criando ? 'new-password' : 'current-password'} placeholder={criando ? 'Pelo menos 8 caracteres' : undefined} />
          </label>
          {erro && <p className="rounded-lg bg-erro-fundo px-3 py-2 text-sm text-erro" role="alert">{erro}</p>}
          <button disabled={enviando}
                  className="rounded-xl bg-confere py-3.5 font-bold text-white hover:bg-[#2559e0] disabled:opacity-60">
            {enviando ? (criando ? 'Criando…' : 'Entrando…') : (criando ? 'Criar conta e entrar' : 'Entrar')}
          </button>
          {cadastroAberto && (
            <p className="text-center text-sm text-apoio">
              {criando ? 'Já tem conta? ' : 'Sua empresa ainda não usa a Concilia AI? '}
              <button type="button" onClick={() => { setModo(criando ? 'entrar' : 'criar'); setErro('') }}
                      className="font-bold text-tinta hover:underline">
                {criando ? 'Entrar' : 'Criar conta'}
              </button>
            </p>
          )}
        </form>
        <p className="mt-16 text-xs text-suave">© 2026 Concilia AI · Privacidade e LGPD</p>
      </main>

      {/* Painel do layout do Figma: chamada no alto e o dashboard saindo pela borda direita. */}
      {/* O dashboard ocupa todo o resto do painel e sai pela borda direita e pela de baixo,
          então não sobra faixa azul vazia embaixo, em nenhuma altura de janela. */}
      <section className="relative hidden flex-col overflow-hidden rounded-l-[2.5rem] bg-confere pt-24 pl-16 text-white lg:flex">
        <div className="pointer-events-none absolute -top-24 -right-24 size-[26.25rem] rounded-full border border-white/15" />
        <div className="pointer-events-none absolute -top-8 -right-8 size-[16.25rem] rounded-full border border-white/15" />
        <h2 className="relative max-w-[28.75rem] text-[2.5rem] leading-tight font-extrabold">Confira notas e contratos sem digitar nada.</h2>
        <p className="relative mt-4 max-w-[30rem] text-white/85">
          Escaneie a nota ou envie o arquivo. A Concilia AI identifica, classifica e confere cada documento contra o contrato.
        </p>
        <div className="relative mt-12 min-h-[16rem] flex-1">
          <img src="/previa-dashboard.jpg" alt="Dashboard da Concilia AI com o scanner, os números do lote, as pastas e os documentos"
               className="absolute top-0 left-0 min-h-full w-[60rem] max-w-none rounded-tl-[1.125rem] object-cover object-left-top shadow-[0_24px_60px_rgba(5,20,64,0.35)]" />
        </div>
      </section>
    </div>
  )
}
