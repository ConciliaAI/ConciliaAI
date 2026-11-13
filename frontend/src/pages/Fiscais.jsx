import { useEffect, useState } from 'react'
import { api } from '../api'

const MODELOS = { '55': 'NF-e · Produto', '65': 'NFC-e · Consumidor', '57': 'CT-e · Transporte' }
const ROTULOS = {
  numero: 'Número', serie: 'Série', emissao: 'Emissão', saida_entrada: 'Saída / entrada',
  natureza_operacao: 'Natureza da operação', tipo_operacao: 'Tipo de operação',
  finalidade: 'Finalidade', ambiente: 'Ambiente', uf_codigo: 'Código da UF',
  municipio_fato_gerador: 'Município do fato gerador', modelo: 'Modelo',
  emitente: 'Emitente', destinatario: 'Destinatário', remetente: 'Remetente',
  expedidor: 'Expedidor', recebedor: 'Recebedor', tomador: 'Tomador',
  valor_total: 'Valor total', valor_receber: 'Valor a receber',
  chave_acesso: 'Chave de acesso', status_chave: 'Validação da chave',
  pagamentos: 'Pagamentos', cobranca: 'Cobrança', transporte: 'Transporte',
  totais: 'Totais', tributos: 'Tributos', carga: 'Carga', componentes_valor: 'Componentes do valor',
  modalidade_frete: 'Modalidade do frete', modal: 'Modalidade de transporte',
  modal_rodoviario: 'Dados rodoviários', consumidor_identificado: 'Consumidor identificado',
  presenca_comprador: 'Presença do comprador', qr_code: 'QR Code',
  troco: 'Troco', informacoes_complementares: 'Informações complementares',
}
const rotulo = (chave) => ROTULOS[chave] || chave.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase())
const legivel = (valor) => valor === null || valor === undefined || valor === '' ? '—'
  : typeof valor === 'boolean' ? (valor ? 'Sim' : 'Não') : String(valor)
const DATA_BR = /^\d{4}-\d{2}-\d{2}/
function mostrarData(v) {
  if (!v || !DATA_BR.test(v)) return legivel(v)
  const [ano, mes, dia] = v.slice(0, 10).split('-')
  return `${dia}/${mes}/${ano}${v.length > 10 ? ' · ' + v.slice(11) : ''}`
}

function Valor({ valor }) {
  if (Array.isArray(valor)) {
    if (!valor.length) return <span className="text-apoio">—</span>
    return <div className="grid gap-2">{valor.map((item, i) =>
      <div key={i} className="rounded-lg bg-papel p-2"><Valor valor={item} /></div>)}</div>
  }
  if (valor && typeof valor === 'object') {
    return <dl className="grid gap-1.5">
      {Object.entries(valor).filter(([, v]) => v !== null && v !== '').map(([k, v]) =>
        <div key={k} className="grid gap-1 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <dt className="font-semibold text-tinta">{rotulo(k)}</dt>
          <dd className="min-w-0 break-words text-apoio"><Valor valor={v} /></dd>
        </div>)}
    </dl>
  }
  return <span className="break-all">{legivel(valor)}</span>
}

function Secao({ titulo, children }) {
  return <section className="rounded-2xl border border-borda p-5">
    <h2 className="mb-3 font-bold">{titulo}</h2>{children}
  </section>
}

function voltar() {
  window.location.hash = 'fiscais'
}

export default function Fiscais({ ws, id }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [modelo, setModelo] = useState('')

  useEffect(() => {
    if (!ws && !id) return
    let ativo = true
    setDados(null)
    setErro('')
    const url = id ? `/api/documentos-fiscais/${id}` :
      `/api/ws/${ws}/documentos-fiscais${modelo ? `?modelo=${modelo}` : ''}`
    api.get(url).then(r => { if (ativo) setDados(r) })
      .catch(e => { if (ativo) setErro(e.message || 'Falha ao consultar documentos fiscais') })
    return () => { ativo = false }
  }, [ws, id, modelo])

  if (erro) return <div className="grid gap-3">
    {id && <button type="button" onClick={voltar} className="justify-self-start text-sm font-semibold text-confere hover:underline">← Voltar aos XML fiscais</button>}
    <p role="alert" className="rounded-xl bg-erro-fundo p-4 text-erro">{erro}</p>
  </div>
  if (!dados) return <p className="text-apoio" role="status">Carregando documentos fiscais…</p>

  if (!id) return <div className="grid gap-5">
    <header>
      <h1 className="text-3xl font-bold">Documentos fiscais XML</h1>
      <p className="mt-1 text-sm text-apoio">NF-e (55), NFC-e (65) e CT-e (57), interpretados diretamente do XML.</p>
    </header>
    <label className="flex items-center gap-3 text-sm font-semibold">
      Modelo fiscal
      <select className="rounded-xl border border-borda bg-white px-4 py-2" value={modelo} onChange={e => setModelo(e.target.value)}>
        <option value="">Todos os modelos</option>
        {Object.entries(MODELOS).map(([m, l]) => <option key={m} value={m}>{l}</option>)}
      </select>
    </label>
    {dados.length === 0 ? <p className="rounded-2xl border border-borda p-6 text-apoio">Nenhum XML desse modelo foi importado. Use “Enviar documentos”.</p>
      : <div className="overflow-x-auto rounded-2xl border border-borda">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <thead className="bg-papel text-xs text-apoio"><tr>
            <th className="p-3">Modelo</th><th className="p-3">Número</th>
            <th className="p-3">Emitente</th><th className="p-3">Emissão</th>
            <th className="p-3">Arquivo</th><th className="p-3">Ações</th>
          </tr></thead>
          <tbody>{dados.map(d => <tr className="border-t border-borda" key={d.id}>
            <td className="p-3 font-semibold">{MODELOS[d.modelo] || d.modelo}</td>
            <td className="p-3">{legivel(d.numero)}</td>
            <td className="p-3">{legivel(d.emissor)}</td>
            <td className="p-3">{mostrarData(d.emissao)}</td>
            <td className="p-3">{legivel(d.nome_arquivo)}</td>
            <td className="p-3"><a className="font-bold text-confere hover:underline" href={`#fiscal-${d.id}`}>Abrir detalhes</a></td>
          </tr>)}</tbody>
        </table>
      </div>}
    <p className="text-xs text-apoio">Importação XML não comprova autorização, autenticidade ou situação atual na SEFAZ.</p>
  </div>

  const d = dados
  const campos = d.campos || {}
  const resumo = ['numero', 'serie', 'emissao', 'natureza_operacao', 'valor_total', 'valor_receber', 'chave_acesso', 'status_chave']
  const participantes = ['emitente', 'destinatario', 'remetente', 'expedidor', 'recebedor', 'tomador']
  const grupos = ['totais', 'totais_complementares', 'tributos', 'carga', 'componentes_valor',
    'transporte', 'modal_rodoviario', 'pagamentos', 'cobranca']
  const outros = Object.keys(campos).filter(x => ![...resumo, ...participantes, ...grupos].includes(x))
  const linha = (k) => <div key={k} className="grid gap-1 border-b border-borda py-2 last:border-0 sm:grid-cols-[12rem_minmax(0,1fr)]">
    <dt className="font-semibold">{rotulo(k)}</dt>
    <dd className="min-w-0 break-words text-apoio">
      {k === 'emissao' ? mostrarData(campos[k]) : <Valor valor={campos[k]} />}
    </dd>
  </div>
  return <div className="grid gap-5">
    <button type="button" onClick={voltar}
      className="justify-self-start rounded-lg px-2 py-1 text-sm font-bold text-confere hover:bg-nevoa focus-visible:outline focus-visible:outline-2 focus-visible:outline-confere">
      ← Voltar aos XML fiscais
    </button>
    <header>
      <h1 className="text-3xl font-bold">{MODELOS[d.modelo] || d.tipo} nº {legivel(campos.numero)}</h1>
      <p className="mt-1 text-sm text-apoio">Arquivo: {d.nome_arquivo} · Leiaute {d.versao || 'não informado'} · Modelo {d.modelo}</p>
    </header>
    <Secao titulo="Validação e situação fiscal">
      <p className="text-sm">Esquema XSD: <b>{d.validacao?.xsd || 'não executado'}</b> · {d.validacao?.motivo_xsd}</p>
      <p className="mt-2 text-sm">Protocolo informado no arquivo: <b>{legivel(d.protocolo?.codigo)}</b> · {legivel(d.protocolo?.mensagem)}</p>
      <p className="mt-2 text-xs text-apoio">Não foi realizada consulta online nem verificação da assinatura pela SEFAZ. A presença do protocolo no XML não confirma autenticidade.</p>
      {d.avisos?.length > 0 && <ul className="mt-3 list-disc pl-5 text-sm text-ambar-texto">
        {d.avisos.map((x, i) => <li key={i}>{x}</li>)}</ul>}
    </Secao>
    <Secao titulo="Informações principais"><dl>{resumo.filter(k => k in campos).map(linha)}</dl></Secao>
    {participantes.some(k => campos[k] && Object.values(campos[k]).some(v => v)) &&
      <Secao titulo="Participantes"><dl>{participantes.filter(k => campos[k] && Object.values(campos[k]).some(v => v)).map(linha)}</dl></Secao>}
    {d.itens?.length > 0 && <Secao titulo={`Itens da nota (${d.itens.length})`}>
      <div className="overflow-x-auto"><table className="w-full min-w-[35rem] text-left text-sm">
        <thead className="bg-papel"><tr><th className="p-2">Código</th><th className="p-2">Descrição</th>
          <th className="p-2">NCM</th><th className="p-2">CFOP</th><th className="p-2">Quantidade</th><th className="p-2">Valor</th></tr></thead>
        <tbody>{d.itens.map((item, i) => <tr key={i} className="border-t border-borda">
          <td className="p-2">{legivel(item.codigo)}</td><td className="p-2">{legivel(item.descricao)}</td>
          <td className="p-2">{legivel(item.ncm)}</td><td className="p-2">{legivel(item.cfop)}</td>
          <td className="p-2">{legivel(item.quantidade)}</td><td className="p-2">{legivel(item.valor_produtos)}</td>
        </tr>)}</tbody>
      </table></div>
    </Secao>}
    {grupos.filter(k => campos[k] != null).map(k => <Secao key={k} titulo={rotulo(k)}>
      <div className="text-sm"><Valor valor={campos[k]} /></div></Secao>)}
    {d.referencias?.length > 0 && <Secao titulo="Documentos referenciados">
      <Valor valor={d.referencias} />
    </Secao>}
    {outros.length > 0 && <Secao titulo="Outras informações"><dl>{outros.map(linha)}</dl></Secao>}
    <details className="rounded-2xl border border-borda p-5">
      <summary className="cursor-pointer font-bold">Origem e rastreabilidade dos campos</summary>
      <dl className="mt-3 grid gap-3 text-sm">
        {Object.entries(d.proveniencia || {}).map(([campo, p]) =>
          <div key={campo} className="break-words border-b border-borda pb-2">
            <dt className="font-semibold">{campo}</dt>
            <dd className="text-apoio">{p.caminho_xml} · original: {p.valor_original}</dd>
          </div>)}
      </dl>
    </details>
  </div>
}
