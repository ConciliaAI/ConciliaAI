import { useRef } from 'react'
import Icone from './Icone'

const FORMATOS = ['NF-e', 'NFS-e', 'PDF', 'XML', 'Foto', 'TIFF', 'ZIP']
const ACEITOS = '.xml,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.zip,.bmp,.webp'

// O scanner (câmera/aparelho) é feito por outra pessoa do time: aqui fica o ponto de entrada (aoEscanear).
export default function BlocoScanner({ aoEscanear, aoEnviarArquivos, enviando }) {
  const entrada = useRef(null)
  return (
    <section className="flex flex-col gap-6 rounded-2xl bg-noite p-6 text-white md:min-h-[9.25rem] md:flex-row md:items-center md:px-7 md:py-0">
      <span className="grid size-[4.75rem] shrink-0 place-items-center rounded-[1.125rem] bg-confere">
        <Icone nome="scanner" className="size-10" />
      </span>
      <div className="grid min-w-0 flex-1 gap-1.5">
        <p className="text-[0.6875rem] font-bold tracking-[0.12em] text-[#8CB3FF]">SCANNER</p>
        <h2 className="text-2xl font-bold">Leia a nota fiscal que está na sua mão</h2>
        <p className="text-sm text-white/70">
          Aponte a câmera ou use o scanner conectado. A Concilia AI identifica o documento, classifica e relaciona com o contrato na hora.
        </p>
        <div className="flex flex-wrap gap-1.5 pt-1.5">
          {FORMATOS.map((f) => <span key={f} className="rounded-md bg-white/10 px-2 py-0.5 text-[0.6875rem] font-semibold text-white/85">{f}</span>)}
        </div>
      </div>
      <div className="grid gap-2.5 md:w-[13.25rem]">
        <button onClick={aoEscanear}
                className="flex items-center justify-center gap-2 rounded-xl bg-confere px-5 py-3 text-sm font-bold hover:bg-[#2559e0]">
          <Icone nome="camera" className="size-[1.125rem]" />Escanear agora
        </button>
        <button onClick={() => entrada.current?.click()} disabled={enviando}
                className="flex items-center justify-center gap-2 rounded-xl border border-white/35 px-5 py-3 text-sm font-bold hover:bg-white/8 disabled:opacity-60">
          <Icone nome="enviar" className="size-[1.125rem]" />{enviando ? 'Enviando…' : 'Enviar arquivo'}
        </button>
        <input ref={entrada} type="file" multiple accept={ACEITOS} className="hidden"
               onChange={(e) => { if (e.target.files.length) aoEnviarArquivos(e.target.files); e.target.value = '' }} />
      </div>
    </section>
  )
}
