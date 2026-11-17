// Chamadas à API da plataforma (app/main.py). A sessão vai no cookie, então basta mandar as credenciais.

export class ErroApi extends Error {
  constructor(mensagem, status) {
    super(mensagem)
    this.status = status
  }
}

async function chamar(url, opcoes = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opcoes })
  const dados = await r.json().catch(() => ({}))
  if (!r.ok) throw new ErroApi(dados.detail || 'Algo deu errado. Tente de novo.', r.status)
  return dados
}

export const api = {
  get: (url) => chamar(url),
  post: (url, corpo) =>
    chamar(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo ?? {}) }),
  enviar: (url, formData) => chamar(url, { method: 'POST', body: formData }),
  excluir: (url) => chamar(url, { method: 'DELETE' }),
}

// Limite de documentos por conta (decisão da reunião de novembro de 2026).
export const LIMITE_DOCUMENTOS = 100_000
