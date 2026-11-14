import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import Icone from '../components/Icone'

// Configurações, no mesmo desenho das telas do Figma (cartões com borda, títulos em Plus Jakarta, azul confere).
// As do cliente (IA, regras, dados protegidos, tipos) valem para o workspace aberto; usuários e integrações, para a conta.

const ABAS = [
  ['geral', 'Geral'],
  ['protegidos', 'Dados protegidos'],
  ['tipos', 'Tipos de documento'],
  ['usuarios', 'Usuários'],
  ['erp', 'Integração com ERP'],
  ['acerto', 'Acerto da IA'],
]
const PERFIS = { admin: 'Administrador', revisor: 'Revisor', operador: 'Operador' }
const PROTEGIDOS = [
  ['cpf', 'CPF e RG', 'Números de documento pessoal'],
  ['banco', 'Dados bancários', 'Agência e conta'],
  ['saude', 'Informações de saúde', 'CID e diagnósticos'],
  ['endereco', 'Endereço', 'Rua e número'],
  ['contato', 'Telefone e e-mail', 'Contato pessoal'],
]
const REGRAS = [
  ['Fornecedor sem contrato', 'crítica', 'Nenhum contrato para o CNPJ do prestador.'],
  ['Valor acima do contratado', 'alta', 'Considera os aditivos vigentes na data da nota e a tolerância abaixo.'],
  ['Fora da vigência', 'alta', 'Nota emitida antes ou depois do contrato.'],
  ['Nota duplicada', 'alta', 'Mesmo número do mesmo prestador.'],
  ['Serviço diferente', 'média', 'Descrição sem relação com o objeto do contrato.'],
  ['Outro tomador', 'média', 'Nota emitida para outro CNPJ.'],
]

const campo = 'w-full rounded-xl border border-borda bg-white px-4 py-2.5 text-sm outline-none focus:border-confere focus:ring-2 focus:ring-confere/25 disabled:bg-papel'
const botao = 'flex h-10 w-fit items-center gap-2 rounded-full bg-confere px-5 text-sm font-bold text-white hover:bg-[#2559e0] disabled:opacity-60'

function Cartao({ titulo, descricao, children, acao }) {
  return (
    <section className="grid content-start gap-4 rounded-[1.25rem] border border-[#E3E7EF] p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[1.0625rem] font-extrabold">{titulo}</h2>
          {descricao && <p className="mt-1 text-sm text-apoio">{descricao}</p>}
        </div>
        {acao}
      </div>
      {children}
    </section>
  )
}

function Interruptor({ ligado, aoMudar, rotulo, detalhe, desabilitado }) {
  return (
    <label className={`flex items-center justify-between gap-4 border-t border-borda py-3 first:border-t-0 first:pt-0 ${desabilitado ? 'opacity-70' : 'cursor-pointer'}`}>
      <span className="grid">
        <b className="text-sm">{rotulo}</b>
        {detalhe && <span className="text-xs text-apoio">{detalhe}</span>}
      </span>
      <span className="relative inline-flex shrink-0">
        <input type="checkbox" className="peer sr-only" checked={ligado} disabled={desabilitado}
               onChange={(e) => aoMudar(e.target.checked)} aria-label={rotulo} />
        <span className="h-6 w-11 rounded-full bg-borda transition-colors peer-checked:bg-confere peer-focus-visible:ring-2 peer-focus-visible:ring-confere/40" />
        <span className="absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  )
}

function Aviso({ aviso, aoFechar }) {
  if (!aviso) return null
  return (
    <p className={`flex items-start justify-between gap-4 rounded-xl px-4 py-3 text-sm ${aviso.erro ? 'bg-erro-fundo text-erro' : 'bg-nevoa text-tinta'}`} role="status">
      {aviso.texto}
      <button onClick={aoFechar} aria-label="Fechar aviso"><Icone nome="fechar" className="size-4" /></button>
    </p>
  )
}

// ------------------------------------------------------------------ Geral
function Geral({ ws, cliente, dados, admin, salvar }) {
  const c = dados.config
  const [limiar, setLimiar] = useState(+c.limiar)
  const [tolerancia, setTolerancia] = useState(+c.tolerancia)
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Cartao titulo="Cliente aberto" descricao="Estas configurações valem só para este workspace. Troque de cliente na barra do topo.">
        <dl className="grid gap-2 text-sm">
          {[['Nome', cliente?.nome], ['CNPJ', cliente?.cnpj], ['Setor', cliente?.setor], ['Identificador', ws]].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 border-t border-borda pt-2 first:border-t-0 first:pt-0">
              <dt className="text-apoio">{k}</dt><dd className="truncate font-semibold">{v || '—'}</dd>
            </div>
          ))}
        </dl>
      </Cartao>

      <Cartao titulo="Inteligência artificial"
              acao={<span className={`rounded-full px-2.5 py-1 text-xs font-bold ${dados.claude_configurado ? 'bg-ok-fundo text-ok' : 'bg-papel text-apoio'}`}>
                {dados.claude_configurado ? 'Pronto' : 'Desligado'}</span>}
              descricao={dados.claude_configurado
                ? `Chave encontrada. Modelo: ${dados.modelo}.`
                : 'Sem chave: a leitura usa OCR e regras locais. Para ligar, coloque ANTHROPIC_API_KEY no .env e reinicie.'}>
        <Interruptor rotulo="Usar o Claude quando houver chave" detalhe="Lê a imagem e o texto da página juntos."
                     ligado={c.usar_claude === '1'} desabilitado={!admin} aoMudar={(v) => salvar({ usar_claude: v })} />
        <div className="grid gap-2 border-t border-borda pt-3">
          <b className="text-sm">Perguntar quando a confiança ficar abaixo de <span className="text-confere">{limiar}%</span></b>
          <input type="range" min="50" max="95" step="1" value={limiar} disabled={!admin} className="w-full accent-confere"
                 onChange={(e) => setLimiar(+e.target.value)} onPointerUp={() => salvar({ limiar })} onKeyUp={() => salvar({ limiar })}
                 aria-label="Limite de confiança" />
          <span className="text-xs text-apoio">Acima disso, o documento entra na conferência sem ninguém olhar. Vale para os próximos envios.</span>
        </div>
      </Cartao>

      <Cartao titulo="Regras de conferência" descricao="As regras são código, não opinião da IA: cada divergência diz qual regra falhou e os valores.">
        <div className="grid gap-2">
          <b className="text-sm">Tolerância de valor: <span className="text-confere">{tolerancia.toLocaleString('pt-BR')}%</span></b>
          <input type="range" min="0" max="10" step="0.5" value={tolerancia} disabled={!admin} className="w-full accent-confere"
                 onChange={(e) => setTolerancia(+e.target.value)} onPointerUp={() => salvar({ tolerancia }, 'Tolerância salva e conferência refeita.')}
                 onKeyUp={() => salvar({ tolerancia }, 'Tolerância salva e conferência refeita.')} aria-label="Tolerância de valor" />
          <span className="text-xs text-apoio">Diferença aceita acima do valor mensal do contrato (somado aos aditivos vigentes) antes de virar divergência. Ao mudar, a conferência é refeita na hora.</span>
        </div>
        <ul className="grid gap-2 border-t border-borda pt-3 text-sm">
          {REGRAS.map(([nome, gravidade, texto]) => (
            <li key={nome} className="flex items-start gap-3">
              <span className={`mt-0.5 rounded-full px-2 py-0.5 text-[0.6875rem] font-bold uppercase ${gravidade === 'crítica' ? 'bg-erro-fundo text-erro' : gravidade === 'alta' ? 'bg-ambar-fundo text-ambar-texto' : 'bg-papel text-apoio'}`}>{gravidade}</span>
              <span><b>{nome}:</b> <span className="text-apoio">{texto}</span></span>
            </li>
          ))}
        </ul>
      </Cartao>
    </div>
  )
}

// ------------------------------------------------------------------ Dados protegidos
function Protegidos({ dados, admin, salvar }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <Cartao titulo="O que fica escondido" descricao="Escondidos na tela, na busca, nas imagens e nos PDFs deste cliente.">
        <div>
          {PROTEGIDOS.map(([k, rotulo, detalhe]) => (
            <Interruptor key={k} rotulo={rotulo} detalhe={detalhe} ligado={dados.config[k] === '1'} desabilitado={!admin}
                         aoMudar={(v) => salvar({ [k]: v })} />
          ))}
        </div>
      </Cartao>
      <Cartao titulo="Ver o original" descricao="Só revisores e administradores veem um documento sem máscara, e precisam informar o motivo. Cada acesso fica registrado.">
        <p className="font-titulo text-[2.125rem] leading-none font-extrabold">{dados.acessos}</p>
        <p className="text-sm text-apoio">acesso(s) a dados protegidos até agora. A lista completa está em Relatórios → Acessos a dados protegidos.</p>
        <a href="#relatorios" className="text-sm font-bold text-tinta hover:underline">Abrir relatórios →</a>
      </Cartao>
    </div>
  )
}

// ------------------------------------------------------------------ Tipos de documento
function Tipos({ ws, dados, admin, recarregar, avisar }) {
  const [nome, setNome] = useState('')
  const [titulos, setTitulos] = useState('')
  const [palavras, setPalavras] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function ensinar(e) {
    e.preventDefault()
    setEnviando(true)
    try {
      await api.post(`/api/ws/${ws}/tipos`, { nome, titulos, palavras })
      avisar(`Tipo “${nome}” adicionado. A IA passa a reconhecer nos próximos envios.`)
      setNome(''); setTitulos(''); setPalavras('')
      await recarregar()
    } catch (err) {
      avisar(err.message, true)
    } finally {
      setEnviando(false)
    }
  }
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Cartao titulo="Tipos que a IA reconhece" descricao="O lote é separado nestes tipos. Contratos, aditivos e notas entram na conferência.">
        <ul className="grid gap-2">
          {dados.tipos.map((t) => (
            <li key={t.id} className="rounded-xl border border-borda px-4 py-3">
              <b className="text-sm">{t.nome}</b>
              <p className="mt-1 line-clamp-2 text-xs text-apoio">{[...t.titulos, ...t.palavras].slice(0, 8).join(' · ') || 'Sem palavras-chave'}</p>
            </li>
          ))}
        </ul>
      </Cartao>
      <Cartao titulo="Ensinar um novo tipo" descricao="Ex.: ordem de compra, boletim de medição de um cliente específico. Vale só para este workspace.">
        {admin ? (
          <form onSubmit={ensinar} className="grid gap-3">
            <label className="grid gap-1.5 text-sm font-medium">Nome
              <input className={campo} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Ordem de compra" />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">Títulos que aparecem no topo
              <input className={campo} value={titulos} onChange={(e) => setTitulos(e.target.value)} placeholder="Separados por vírgula" />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">Palavras típicas
              <input className={campo} value={palavras} onChange={(e) => setPalavras(e.target.value)} placeholder="Separadas por vírgula" />
            </label>
            <button className={botao} disabled={enviando}><Icone nome="mais" className="size-4" />{enviando ? 'Adicionando…' : 'Adicionar tipo'}</button>
          </form>
        ) : <p className="rounded-xl bg-papel p-4 text-sm text-apoio">Só o administrador ensina tipos novos.</p>}
      </Cartao>
    </div>
  )
}

// ------------------------------------------------------------------ Usuários da conta
function Usuarios({ conta, eu, admin, avisar }) {
  const [lista, setLista] = useState(null)
  const [form, setForm] = useState({ nome: '', usuario: '', senha: '', perfil: 'operador' })
  const [enviando, setEnviando] = useState(false)
  const carregar = useCallback(() => api.get('/api/usuarios').then(setLista).catch(() => setLista([])), [])
  useEffect(() => { if (admin) carregar() }, [admin, carregar])

  async function cadastrar(e) {
    e.preventDefault()
    setEnviando(true)
    try {
      const u = await api.post('/api/usuarios', form)
      avisar(`${u.nome} pode entrar com o usuário “${u.usuario}”.`)
      setForm({ nome: '', usuario: '', senha: '', perfil: 'operador' })
      await carregar()
    } catch (err) {
      avisar(err.message, true)
    } finally {
      setEnviando(false)
    }
  }

  if (!admin) {
    return <Cartao titulo="Usuários da empresa"><p className="text-sm text-apoio">Você entrou como {PERFIS[eu.perfil]?.toLowerCase()}. Só o administrador vê e cadastra usuários.</p></Cartao>
  }
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <Cartao titulo={`Usuários de ${conta?.nome || 'sua empresa'}`} descricao="Todos enxergam os workspaces da empresa. O perfil define o que cada um pode fazer.">
        {!lista ? <p className="text-sm text-apoio">Carregando…</p> : (
          <ul className="grid gap-2">
            {lista.map((u) => (
              <li key={u.usuario} className="flex items-center justify-between gap-3 rounded-xl border border-borda px-4 py-3">
                <span className="grid min-w-0">
                  <b className="truncate text-sm">{u.nome}{u.usuario === eu.usuario && <span className="font-normal text-suave"> (você)</span>}</b>
                  <span className="text-xs text-apoio">@{u.usuario}</span>
                </span>
                <span className="rounded-full bg-nevoa px-2.5 py-1 text-xs font-bold text-tinta">{PERFIS[u.perfil] || u.perfil}</span>
              </li>
            ))}
          </ul>
        )}
        <ul className="grid gap-1 border-t border-borda pt-3 text-xs text-apoio">
          <li><b className="text-noite">Operador:</b> envia documentos e consulta.</li>
          <li><b className="text-noite">Revisor:</b> também decide dúvidas e divergências e pode ver dados protegidos (com motivo).</li>
          <li><b className="text-noite">Administrador:</b> também cria workspaces, usuários, integrações e muda as configurações.</li>
        </ul>
      </Cartao>
      <Cartao titulo="Cadastrar pessoa">
        <form onSubmit={cadastrar} className="grid gap-3">
          <label className="grid gap-1.5 text-sm font-medium">Nome
            <input className={campo} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Usuário
            <input className={campo} value={form.usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} placeholder="Ex.: joao.lima" autoComplete="off" />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Senha inicial
            <input className={campo} type="password" value={form.senha} onChange={(e) => setForm({ ...form, senha: e.target.value })} placeholder="Pelo menos 8 caracteres" autoComplete="new-password" />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Perfil
            <select className={campo} value={form.perfil} onChange={(e) => setForm({ ...form, perfil: e.target.value })}>
              {Object.entries(PERFIS).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
            </select>
          </label>
          <button className={botao} disabled={enviando}><Icone nome="mais" className="size-4" />{enviando ? 'Cadastrando…' : 'Cadastrar'}</button>
        </form>
      </Cartao>
    </div>
  )
}

// ------------------------------------------------------------------ Integração com ERP
function Integracoes({ ws, cliente, admin, avisar }) {
  const [lista, setLista] = useState(null)
  const [nome, setNome] = useState('')
  const [token, setToken] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const carregar = useCallback(() => api.get('/api/integracoes').then(setLista).catch(() => setLista([])), [])
  useEffect(() => { if (admin) carregar() }, [admin, carregar])

  async function criar(e) {
    e.preventDefault()
    setEnviando(true)
    try {
      const r = await api.post('/api/integracoes', { nome, ws })
      setToken(r.token)
      setNome('')
      await carregar()
    } catch (err) {
      avisar(err.message, true)
    } finally {
      setEnviando(false)
    }
  }
  async function revogar(i) {
    try {
      await api.post(`/api/integracoes/${i.id}/revogar`)
      avisar(`Chave “${i.nome}” revogada: o ERP não consegue mais enviar com ela.`)
      await carregar()
    } catch (err) {
      avisar(err.message, true)
    }
  }

  if (!admin) return <Cartao titulo="Integração com ERP"><p className="text-sm text-apoio">Só o administrador cria e revoga as chaves de integração.</p></Cartao>
  const doCliente = (lista || []).filter((i) => i.workspace === ws)
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <Cartao titulo={`Chaves de ${cliente?.nome || 'este cliente'}`}
              descricao="O ERP envia documentos e busca os resultados pela API /api/erp/v1, sem abrir a tela. Cada chave vale só para este workspace.">
        {!lista ? <p className="text-sm text-apoio">Carregando…</p> : doCliente.length === 0 ? (
          <p className="rounded-xl bg-papel p-4 text-sm text-apoio">Nenhuma chave ainda. Crie uma ao lado e configure no ERP do cliente.</p>
        ) : (
          <ul className="grid gap-2">
            {doCliente.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-borda px-4 py-3">
                <span className="grid min-w-0">
                  <b className="truncate text-sm">{i.nome}</b>
                  <span className="text-xs text-apoio">
                    {i.token_prefix}… · criada em {new Date(i.criada_em).toLocaleDateString('pt-BR')}
                    {i.ultimo_acesso ? ` · último uso ${new Date(i.ultimo_acesso).toLocaleString('pt-BR')}` : ' · ainda não usada'}
                  </span>
                </span>
                {i.ativa ? (
                  <button onClick={() => revogar(i)} className="rounded-full border border-borda px-3 py-1.5 text-xs font-bold text-erro hover:bg-erro-fundo">Revogar</button>
                ) : <span className="rounded-full bg-papel px-2.5 py-1 text-xs font-bold text-apoio">Revogada</span>}
              </li>
            ))}
          </ul>
        )}
        <p className="border-t border-borda pt-3 text-xs text-apoio">Rotas: enviar (POST /api/erp/v1/documents, com Idempotency-Key), listar, situação e resultados. Detalhes em docs/ERP_API_V1.md.</p>
      </Cartao>
      <Cartao titulo="Nova chave">
        {token ? (
          <div className="grid gap-3">
            <p className="rounded-xl bg-ambar-fundo p-3 text-sm text-ambar-texto"><b>Copie agora:</b> esta chave não aparece de novo. Guarde no ERP, nunca em e-mail ou chat.</p>
            <code className="block rounded-xl bg-noite p-3 text-xs break-all text-white">{token}</code>
            <div className="flex gap-2">
              <button className={botao} onClick={() => navigator.clipboard?.writeText(token).then(() => avisar('Chave copiada.'))}>Copiar</button>
              <button className="h-10 rounded-full border border-borda px-5 text-sm font-bold hover:bg-papel" onClick={() => setToken(null)}>Pronto</button>
            </div>
          </div>
        ) : (
          <form onSubmit={criar} className="grid gap-3">
            <label className="grid gap-1.5 text-sm font-medium">Nome da integração
              <input className={campo} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: ERP do cliente – produção" />
            </label>
            <p className="text-xs text-apoio">A chave pode enviar documentos e ler resultados deste workspace.</p>
            <button className={botao} disabled={enviando || !nome.trim()}><Icone nome="mais" className="size-4" />{enviando ? 'Criando…' : 'Criar chave'}</button>
          </form>
        )}
      </Cartao>
    </div>
  )
}

// ------------------------------------------------------------------ Acerto da IA
function Numero({ valor, titulo, texto }) {
  return (
    <div className="grid content-start gap-1 rounded-2xl border border-borda px-5 py-4">
      <p className="text-sm text-apoio">{titulo}</p>
      <p className="font-titulo text-[1.75rem] leading-tight font-bold tabular-nums">{valor ?? '—'}%</p>
      <p className="text-xs text-apoio">{texto}</p>
    </div>
  )
}

function Acerto({ ws, admin, avisar }) {
  const [lista, setLista] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const carregar = useCallback(() => api.get(`/api/ws/${ws}/avaliacoes`).then(setLista).catch(() => setLista([])), [ws])
  useEffect(() => { carregar() }, [carregar])
  const medindo = (lista || []).some((x) => !x.resultado && x.envio.status !== 'recusado')
  useEffect(() => {
    if (!medindo) return
    const t = setTimeout(carregar, 4000)
    return () => clearTimeout(t)
  }, [medindo, lista, carregar])

  async function avaliar() {
    setEnviando(true)
    try {
      await api.post(`/api/ws/${ws}/avaliacao`, {})
      avisar('Lote com gabarito enviado. O resultado aparece aqui quando a leitura terminar (alguns minutos).')
      await carregar()
    } catch (err) {
      avisar(err.message, true)
    } finally {
      setEnviando(false)
    }
  }

  const ultimo = (lista || []).find((x) => x.resultado)
  const r = ultimo?.resultado
  const k = r?.conciliacao
  return (
    <div className="grid gap-4">
      <Cartao titulo="Medir o acerto com um lote de teste"
              descricao="Um lote fictício é gerado com o gabarito (onde começa cada documento, qual o tipo e quais notas têm problema). A Concilia lê sem ver o gabarito, e aqui comparamos."
              acao={admin && <button className={botao} onClick={avaliar} disabled={enviando || medindo}>{medindo ? 'Medindo…' : enviando ? 'Gerando…' : 'Gerar lote e medir'}</button>}>
        {!admin && <p className="text-sm text-apoio">Só o administrador inicia uma avaliação.</p>}
        {!r && <p className="rounded-xl bg-papel p-4 text-sm text-apoio">{medindo ? 'Lendo o lote de teste… o resultado aparece quando terminar.' : 'Nenhuma avaliação ainda neste workspace.'}</p>}
      </Cartao>
      {r && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {k && <Numero titulo="Problemas encontrados" valor={k.cobertura} texto={`${k.detectadas} de ${k.divergencias_esperadas} notas com problema; ${k.regra_certa}% com a regra certa.`} />}
            {k && <Numero titulo="Alarmes corretos" valor={k.precisao} texto={`${k.falsos_alarmes} alarme(s) falso(s).`} />}
            <Numero titulo="Separação dos documentos (F1)" valor={r.fronteira_f1} texto={`Acertou o início de ${r.fronteira_cobertura}% dos documentos.`} />
            <Numero titulo="Documento inteiro certo" valor={r.tipo_correto} texto={`Páginas e tipo corretos nos ${r.documentos_gabarito} documentos do gabarito.`} />
            <Numero titulo="Acerto do que foi aprovado sozinho" valor={r.acerto_automaticos} texto={`${r.enviados_revisao} foram para a revisão humana (${r.pct_revisao}%).`} />
            <Numero titulo="Páginas com o tipo certo" valor={r.paginas_tipo_correto} texto={`${r.paginas} páginas no lote (envio #${ultimo.envio.id}).`} />
          </div>
          {r.erros?.length > 0 && (
            <Cartao titulo="Onde a IA errou no último lote">
              <div className="max-h-[18rem] overflow-auto">
                <table className="w-full text-left text-[0.8125rem]">
                  <thead><tr className="sticky top-0 bg-white text-[0.6875rem] tracking-[0.04em] text-suave uppercase"><th className="py-2 pr-4">Documento</th><th className="pr-4">Páginas</th><th className="pr-4">Certo</th><th>A IA disse</th></tr></thead>
                  <tbody>{r.erros.map((e, i) => (
                    <tr key={i} className="border-t border-borda"><td className="py-2 pr-4">{e.documento}</td><td className="pr-4 tabular-nums">{e.paginas}</td><td className="pr-4">{e.esperado}</td><td>{e.previsto}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </Cartao>
          )}
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ tela
export default function Configuracoes({ ws, cliente, conta, usuario }) {
  const [aba, setAba] = useState(() => new URLSearchParams(window.location.hash.split('?')[1]).get('aba') || 'geral')
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState(null)
  const admin = usuario.perfil === 'admin'
  const avisar = (texto, erro = false) => setAviso({ texto, erro })

  const carregar = useCallback(async () => {
    try {
      setDados(await api.get(`/api/ws/${ws}/config`))
    } catch (e) {
      setErro(e.message)
    }
  }, [ws])
  useEffect(() => { carregar() }, [carregar])

  async function salvar(mudanca, mensagem = 'Configuração salva.') {
    try {
      const config = await api.post(`/api/ws/${ws}/config`, mudanca)
      setDados((d) => ({ ...d, config }))
      avisar(mensagem)
    } catch (e) {
      avisar(e.message, true)
    }
  }

  if (erro) return <p className="rounded-2xl bg-erro-fundo p-6 text-erro">{erro}</p>
  if (!dados) return <p className="text-apoio">Carregando…</p>
  const props = { ws, cliente, conta, dados, admin, salvar, avisar, recarregar: carregar, eu: usuario }
  return (
    <div className="grid grid-cols-1 gap-6">
      <div>
        <h1 className="text-[2.125rem] leading-[1.25] font-bold">Configurações</h1>
        <p className="mt-0.5 text-[0.9375rem] text-apoio">
          {cliente?.nome}{conta?.nome ? ` · ${conta.nome}` : ''}{admin ? '' : ' · só o administrador altera'}
        </p>
      </div>
      <div role="tablist" aria-label="Seções" className="flex gap-1 overflow-x-auto rounded-full bg-papel p-1 [scrollbar-width:none]">
        {ABAS.map(([id, rotulo]) => (
          <button key={id} role="tab" aria-selected={aba === id} onClick={() => { setAba(id); setAviso(null) }}
                  className={`h-9 shrink-0 rounded-full px-4 text-sm font-bold whitespace-nowrap ${aba === id ? 'bg-white text-noite shadow-sm' : 'text-apoio hover:text-noite'}`}>
            {rotulo}
          </button>
        ))}
      </div>
      <Aviso aviso={aviso} aoFechar={() => setAviso(null)} />
      {aba === 'geral' && <Geral {...props} />}
      {aba === 'protegidos' && <Protegidos {...props} />}
      {aba === 'tipos' && <Tipos {...props} />}
      {aba === 'usuarios' && <Usuarios {...props} />}
      {aba === 'erp' && <Integracoes {...props} />}
      {aba === 'acerto' && <Acerto {...props} />}
    </div>
  )
}
