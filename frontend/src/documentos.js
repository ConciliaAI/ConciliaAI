// Nomes e textos de documento usados em várias telas.

// Nome curto do tipo, para caber em pastas, tabelas e cartões.
const CURTO = {
  'Nota fiscal de serviço': 'Nota fiscal',
  'Contrato de prestação de serviços': 'Contrato',
  'Aditivo contratual': 'Aditivo',
}
export const curto = (tipo) => CURTO[tipo] || tipo

// Nome da pasta, no plural (como no Figma: "Notas fiscais", "Contratos").
const PLURAL = { 'Nota fiscal': 'Notas fiscais', Contrato: 'Contratos', Aditivo: 'Aditivos', Comprovante: 'Comprovantes' }
export const pasta = (tipo) => PLURAL[curto(tipo)] || curto(tipo)

// "NFS-e nº 1.204 · Limpa Bem", com o que foi lido do documento (número e prestador), quando houver.
export function nomeDocumento(d) {
  const campos = d.dados?.campos || {}
  const prefixo = curto(d.tipo) === 'Nota fiscal' ? 'NFS-e' : curto(d.tipo)
  const numero = campos.numero ? `${prefixo} nº ${campos.numero}` : `${curto(d.tipo)} #${d.id}`
  const quem = campos.nome_prestador || d.empresa
  return quem ? `${numero} · ${quem}` : numero
}

// Pergunta curta para cada tipo de dúvida da IA (o "motivo" do servidor costuma ser só "página 3").
export const DUVIDA = {
  tipo: (p) => (p.tipo === 'Não identificado' ? 'Que documento é este?' : `É mesmo ${curto(p.tipo).toLowerCase()}?`),
  fronteira: () => 'Onde este documento começa?',
  integridade: (p) => resumoProblema(p.motivo),
}

// "Página repetida: a página 4 de 9 aparece 2 vezes (...)" -> "Página 4 de 9 repetida"
export function resumoProblema(texto = '') {
  let m = texto.match(/a página (\d+ de \d+) aparece/)
  if (m) return `Página ${m[1]} repetida`
  m = texto.match(/falta[m]? a[s]? página[s]? ([\d, …]+) de (\d+)/)
  if (m) return `Falta a página ${m[1].trim()} de ${m[2]}`
  if (/escaneada duas vezes/.test(texto)) return 'Página escaneada duas vezes'
  return texto || 'Problema nas páginas'
}
