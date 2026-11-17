export default function Logo({ claro = false }) {
  return (
    <div className="flex items-center gap-2.5">
      {/* No fundo escuro, o símbolo escuro sumia: usa a versão clara (quadrado branco). */}
      <img src={claro ? '/simbolo-claro.svg' : '/simbolo.svg'} alt="" className="size-9 rounded-[0.625rem]" />
      <span className={`font-titulo text-[1.375rem] font-extrabold tracking-tight ${claro ? 'text-white' : 'text-noite'}`}>
        concilia<span className="text-confere">.</span>ai
      </span>
    </div>
  )
}
