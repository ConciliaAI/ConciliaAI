// Ícones em linha (traço 1.8), no estilo do layout do Figma.
const CAMINHOS = {
  documentos: <><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 13h6M10 17h6" /></>,
  enviar: <><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" /><path d="M4 15v5h16v-5" /></>,
  revisao: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  contratos: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  relatorios: <><path d="M5 20V10M10 20V4M15 20v-7M20 20v-4" /></>,
  config: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></>,
  ajuda: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.5h.01" /></>,
  sair: <><path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10" /></>,
  busca: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  sino: <><path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z" /><path d="M10 21h4" /></>,
  seta: <><path d="M7 17 17 7M8 7h9v9" /></>,
  mais: <path d="M12 5v14M5 12h14" />,
  baixar: <><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M4 15v5h16v-5" /></>,
  camera: <><path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h2.3l1.5-2.5h7.4L17.2 7h2.3A1.5 1.5 0 0 1 21 8.5v10a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z" /><circle cx="12" cy="13" r="3.6" /></>,
  scanner: <><path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" /><path d="M7 12h10" /></>,
  arquivo: <><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5" /></>,
  filtro: <path d="M4 6h16M7 12h10M10 18h4" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  fechar: <path d="M6 6l12 12M18 6 6 18" />,
  lixeira: <><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
  planilha: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 9.5h16M4 14.5h16M9.5 9.5V20" /></>,
  abaixo: <path d="m6 9 6 6 6-6" />,
  olho:<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
}

export default function Icone({ nome, className = 'size-5' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
         strokeLinejoin="round" className={className} aria-hidden="true">
      {CAMINHOS[nome]}
    </svg>
  )
}
