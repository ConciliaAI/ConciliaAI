import { useState } from 'react'
import Icone from '../components/Icone'

// Ajuda: como a Concilia funciona, do envio ao relatório, e as dúvidas mais comuns. Mesmo desenho das telas do Figma.

const CAMINHO = [
  ['enviar', 'Envie ou escaneie', 'Arraste o lote (PDF, TIFF, foto, ZIP ou XML) ou use “Escanear agora” com a câmera. Pode ser tudo misturado, num arquivo só.'],
  ['documentos', 'A Concilia separa o lote', 'Cada página recebe “começa um novo documento” ou “continua”; as páginas viram documentos com tipo, confiança e texto pesquisável (OCR).'],
  ['revisao', 'Você decide só o que tem dúvida', 'Abaixo do limite de confiança, ou quando uma nota não bate com o contrato, o item vai para a Revisão humana com o motivo e as páginas lado a lado.'],
  ['contratos', 'Contratos viram a referência', 'Número, CNPJ, objeto, valor mensal, vigência e aditivos são lidos dos PDFs. Cada nota é comparada com o contrato do prestador.'],
  ['relatorios', 'Tudo vira planilha', 'Divergências por regra, notas conferidas no mês e planilhas para baixar, com a trilha de quem decidiu o quê.'],
]

const RECURSOS = [
  ['Um workspace por cliente', 'Sua empresa tem uma conta e cria um workspace para cada cliente. Troque de cliente na barra do topo; uma empresa nunca vê os dados de outra.', 'novo-workspace'],
  ['Notas em XML', 'NFS-e é conferida contra o contrato. NF-e, NFC-e e CT-e são lidos direto do XML, sem OCR, e ficam em XML fiscais.', 'fiscais'],
  ['Dados protegidos', 'CPF, conta, saúde, endereço e contato ficam escondidos na tela, na busca, nas imagens e nos PDFs. Ver o original exige motivo.', 'config?aba=protegidos'],
  ['Integração com ERP', 'O ERP do cliente envia documentos e busca os resultados pela API, com uma chave por workspace.', 'config?aba=erp'],
  ['Retomada após falha', 'Cada página é salva ao terminar. Se a conexão cair ou o programa fechar, a leitura continua da próxima página.', 'enviar'],
  ['Acerto medido', 'Um lote de teste com gabarito mede a separação dos documentos e a conferência das notas.', 'config?aba=acerto'],
]

const PERGUNTAS = [
  ['Quais arquivos posso enviar?', 'PDF (digitalizado ou não), TIFF, JPG, PNG, ZIP com vários arquivos e XML de notas fiscais (NFS-e, NF-e, NFC-e e CT-e). Arquivos repetidos são ignorados para não duplicar.'],
  ['O que a Concilia confere numa nota?', 'Seis regras fixas: fornecedor sem contrato, valor acima do contratado (com aditivos e tolerância), fora da vigência, nota duplicada, serviço diferente do objeto e nota para outro tomador.'],
  ['Por que um documento foi para a Revisão humana?', 'Porque a confiança ficou abaixo do limite definido em Configurações, ou porque a nota não bateu com o contrato. O motivo aparece no próprio item, com a página que causou a dúvida.'],
  ['Quem pode fazer o quê?', 'Operador envia e consulta. Revisor também decide dúvidas e divergências e pode ver dados protegidos, informando o motivo. Administrador também cria workspaces, usuários e integrações e muda as configurações.'],
  ['Existe limite de documentos?', 'Sim: até 100 mil documentos por conta, somando todos os workspaces. O uso aparece no quadro do plano, no fim do menu.'],
  ['A Concilia substitui o contador ou o jurídico?', 'Não. Ela aponta as diferenças e mostra de onde vêm; a decisão continua com a equipe. Não substitui análise jurídica, contábil ou tributária.'],
  ['Na Revisão humana, existem atalhos?', 'Sim: as teclas 1, 2 e 3 escolhem as respostas do item aberto.'],
]

export default function Ajuda() {
  const [aberta, setAberta] = useState(0)
  return (
    <div className="grid grid-cols-1 gap-7">
      <div>
        <h1 className="text-[2.125rem] leading-[1.25] font-bold">Ajuda</h1>
        <p className="mt-0.5 text-[0.9375rem] text-apoio">Como a Concilia funciona, do envio do lote à planilha final.</p>
      </div>

      <section className="grid gap-4">
        <h2 className="text-lg font-extrabold">O caminho de um documento</h2>
        <ol className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {CAMINHO.map(([rota, titulo, texto], i) => (
            <li key={rota} className="grid content-start gap-2 rounded-[1.25rem] border border-[#E3E7EF] p-5">
              <span className={`grid size-9 place-items-center rounded-full text-sm font-extrabold ${i === 0 ? 'bg-confere text-white' : 'bg-nevoa text-confere'}`}>{i + 1}</span>
              <h3 className="font-sans text-[0.9375rem] font-bold">{titulo}</h3>
              <p className="text-[0.8125rem] leading-relaxed text-apoio">{texto}</p>
              <a href={`#${rota}`} className="mt-1 text-[0.8125rem] font-bold text-tinta hover:underline">Abrir →</a>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-4">
        <h2 className="text-lg font-extrabold">O que mais a Concilia faz</h2>
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {RECURSOS.map(([titulo, texto, rota]) => (
            <a key={titulo} href={`#${rota}`} className="group grid grid-cols-[2.75rem_minmax(0,1fr)] gap-x-4 rounded-[1.25rem] border border-[#E3E7EF] p-5 hover:border-confere/50">
              <span className="row-span-2 grid size-11 place-items-center rounded-xl bg-nevoa text-confere"><Icone nome="check" className="size-5" /></span>
              <h3 className="font-sans text-[0.9375rem] font-bold group-hover:text-tinta">{titulo}</h3>
              <p className="mt-1 text-[0.8125rem] leading-relaxed text-apoio">{texto}</p>
            </a>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20.5rem]">
        <section className="grid content-start gap-3 rounded-[1.25rem] border border-[#E3E7EF] p-6">
          <h2 className="text-lg font-extrabold">Perguntas frequentes</h2>
          <ul className="grid">
            {PERGUNTAS.map(([pergunta, resposta], i) => (
              <li key={pergunta} className="border-t border-borda first:border-t-0">
                <button type="button" onClick={() => setAberta(aberta === i ? null : i)} aria-expanded={aberta === i}
                        className="flex w-full items-center justify-between gap-4 py-3.5 text-left text-sm font-bold hover:text-tinta">
                  {pergunta}
                  <Icone nome="abaixo" className={`size-4 shrink-0 transition-transform ${aberta === i ? 'rotate-180' : ''}`} />
                </button>
                {aberta === i && <p className="pb-4 text-sm leading-relaxed text-apoio">{resposta}</p>}
              </li>
            ))}
          </ul>
        </section>

        <aside className="grid content-start gap-3 rounded-[1.25rem] bg-noite p-6 text-white">
          <h2 className="text-lg font-bold">Precisa de mais ajuda?</h2>
          <p className="text-sm text-white/70">Fale com quem administra a conta da sua empresa ou com o time da Concilia AI.</p>
          <a href="https://github.com/ConciliaAI/ConciliaAI" target="_blank" rel="noreferrer"
             className="mt-1 flex h-10 w-fit items-center gap-2 rounded-full bg-confere px-5 text-sm font-bold hover:bg-[#2559e0]">
            Ver o projeto no GitHub <Icone nome="seta" className="size-4" />
          </a>
          <p className="mt-2 border-t border-white/10 pt-3 text-xs text-white/60">
            Ferramenta de apoio à conferência documental. Aponta diferenças e mostra de onde elas vêm; não substitui análise jurídica, contábil ou tributária.
          </p>
        </aside>
      </div>
    </div>
  )
}
