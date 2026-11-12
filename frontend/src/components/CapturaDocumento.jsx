import { useCallback, useEffect, useRef, useState } from 'react'
import Icone from './Icone'

export default function CapturaDocumento({ aberto, aoFechar, aoCapturar, enviando }) {
  const [modo, setModo] = useState('camera') // 'camera' | 'preview'
  const [carregando, setCarregando] = useState(true)
  const [erroCamera, setErroCamera] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [arquivoCapturado, setArquivoCapturado] = useState(null)
  const [facingMode, setFacingMode] = useState('environment') // 'environment' (traseira) | 'user' (frontal)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const inputNativoRef = useRef(null)

  // Desliga os sensores da câmera e libera o hardware do dispositivo
  const pararCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop()
        } catch { /* ignora */ }
      })
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }, [])

  // Inicia o stream WebRTC da câmera
  const iniciarCamera = useCallback(async () => {
    pararCamera()

    if (!navigator.mediaDevices?.getUserMedia) {
      setErroCamera(
        'Câmera ao vivo indisponível neste navegador ou sem suporte a WebRTC/HTTPS. Use a câmera nativa abaixo.'
      )
      setCarregando(false)
      return
    }

    try {
      setCarregando(true)
      setErroCamera(null)
      const constraints = {
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      streamRef.current = stream

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        // playsInline garante que não entra em tela cheia forçada no iOS
        await videoRef.current.play().catch(() => {})
      }
      setCarregando(false)
    } catch (err) {
      console.warn('Falha ao acessar câmera WebRTC:', err)
      pararCamera()
      let msg = 'Não foi possível acessar a câmera do dispositivo.'
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        msg = 'Permissão de acesso à câmera negada. Conceda permissão no navegador ou use a câmera nativa.'
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        msg = 'Nenhuma câmera encontrada no dispositivo. Use o seletor de arquivos abaixo.'
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        msg = 'A câmera está sendo usada por outro aplicativo. Feche-o e tente novamente.'
      }
      setErroCamera(msg)
      setCarregando(false)
    }
  }, [facingMode, pararCamera])

  // Inicializa a câmera quando o modal abrir em modo 'camera'
  useEffect(() => {
    let cancelado = false
    if (aberto && modo === 'camera') {
      // Defer inicialização para microtask para evitar render cascata
      Promise.resolve().then(() => {
        if (!cancelado) iniciarCamera()
      })
    } else {
      pararCamera()
    }
    return () => {
      cancelado = true
      pararCamera()
    }
  }, [aberto, modo, iniciarCamera, pararCamera])

  // Limpa URLs de objeto criadas para o preview
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  // Fecha o modal e garante limpeza completa
  const fechar = () => {
    pararCamera()
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    setArquivoCapturado(null)
    setModo('camera')
    setErroCamera(null)
    aoFechar?.()
  }

  // Tira a foto a partir do quadro atual do vídeo
  const capturarFoto = () => {
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight) return

    const canvas = canvasRef.current || document.createElement('canvas')
    const largura = video.videoWidth
    const altura = video.videoHeight
    canvas.width = largura
    canvas.height = altura

    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0, largura, altura)

    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
        const arquivo = new File([blob], `documento-${timestamp}.jpg`, { type: 'image/jpeg' })

        // Desliga a câmera imediatamente para economizar bateria e liberar hardware
        pararCamera()

        if (previewUrl) URL.revokeObjectURL(previewUrl)
        const novaUrl = URL.createObjectURL(blob)
        setPreviewUrl(novaUrl)
        setArquivoCapturado(arquivo)
        setModo('preview')
      },
      'image/jpeg',
      0.92
    )
  }

  // Descarta a foto atual e volta para o visor
  const tirarOutra = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    setArquivoCapturado(null)
    setModo('camera')
  }

  // Confirma a foto capturada e envia para a fila de análise
  const confirmarEnvio = () => {
    if (!arquivoCapturado) return
    pararCamera()
    aoCapturar?.(arquivoCapturado)
    fechar()
  }

  // Fallback para seleção de arquivo via câmera nativa do celular ou galeria
  const lidarComArquivoNativo = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    pararCamera()
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    const novaUrl = URL.createObjectURL(file)
    setPreviewUrl(novaUrl)
    setArquivoCapturado(file)
    setModo('preview')
    e.target.value = ''
  }

  // Alterna entre câmera frontal e traseira
  const alternarCamera = () => {
    setFacingMode((atual) => (atual === 'environment' ? 'user' : 'environment'))
  }

  if (!aberto) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="titulo-captura"
      className="fixed inset-0 z-50 flex flex-col bg-black/95 text-white backdrop-blur-sm select-none"
    >
      {/* Barra de Topo */}
      <header className="relative z-10 flex h-16 shrink-0 items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-xl bg-confere text-white">
            <Icone nome="camera" className="size-5" />
          </span>
          <div>
            <h2 id="titulo-captura" className="text-base font-bold leading-tight">
              {modo === 'preview' ? 'Conferir documento' : 'Fotografar documento'}
            </h2>
            <p className="text-xs text-white/70">
              {modo === 'preview' ? 'Verifique se os dados estão legíveis' : 'Aponte para a nota fiscal ou contrato'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {modo === 'camera' && !erroCamera && (
            <button
              type="button"
              onClick={alternarCamera}
              className="flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 active:scale-95"
              title="Alternar câmera"
              aria-label="Alternar câmera"
            >
              <Icone nome="girar" className="size-5" />
            </button>
          )}
          <button
            type="button"
            onClick={fechar}
            className="flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 active:scale-95"
            aria-label="Fechar captura"
          >
            <Icone nome="fechar" className="size-5" />
          </button>
        </div>
      </header>

      {/* Conteúdo Central: Visor WebRTC ou Preview */}
      <main className="relative flex flex-1 items-center justify-center overflow-hidden p-2 sm:p-4">
        {modo === 'camera' && (
          <div className="relative flex h-full w-full max-w-2xl items-center justify-center overflow-hidden rounded-2xl bg-black">
            {/* Tag video com playsInline obrigatório para iOS */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className={`h-full w-full object-cover transition-opacity duration-300 ${
                carregando || erroCamera ? 'opacity-0' : 'opacity-100'
              }`}
            />

            {/* Canvas oculto para captura em resolução nativa */}
            <canvas ref={canvasRef} className="hidden" />

            {/* Feedback de carregamento */}
            {carregando && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black text-center">
                <div className="size-10 animate-spin rounded-full border-3 border-white/20 border-t-confere" />
                <p className="text-sm font-medium text-white/80">Inicializando a câmera...</p>
              </div>
            )}

            {/* Mensagem de Erro com Fallback imediato */}
            {erroCamera && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-black/90 p-6 text-center">
                <div className="grid size-12 place-items-center rounded-full bg-erro-fundo text-erro">
                  <Icone nome="camera" className="size-6" />
                </div>
                <div className="max-w-md">
                  <p className="text-sm font-semibold text-white">{erroCamera}</p>
                  <p className="mt-1 text-xs text-white/70">
                    Você ainda pode fotografar diretamente usando o aplicativo de câmera nativo do seu celular:
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => inputNativoRef.current?.click()}
                  className="flex items-center gap-2 rounded-xl bg-confere px-5 py-3 text-sm font-bold text-white transition hover:bg-[#2559e0]"
                >
                  <Icone nome="camera" className="size-5" />
                  Abrir Câmera Nativa / Galeria
                </button>
              </div>
            )}

            {/* Moldura Visual de Enquadramento do Documento (Proporção A4) */}
            {!carregando && !erroCamera && (
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center p-6">
                <div className="relative flex aspect-[1/1.414] h-full max-h-[72vh] w-auto max-w-[90vw] flex-col justify-between rounded-2xl border-2 border-dashed border-white/75 shadow-[0_0_0_9999px_rgba(0,0,0,0.55)] transition-all">
                  {/* Cantos reforçados para estilo scanner */}
                  <span className="absolute -top-1 -left-1 size-5 rounded-tl-lg border-t-4 border-l-4 border-confere" />
                  <span className="absolute -top-1 -right-1 size-5 rounded-tr-lg border-t-4 border-r-4 border-confere" />
                  <span className="absolute -bottom-1 -left-1 size-5 rounded-bl-lg border-b-4 border-l-4 border-confere" />
                  <span className="absolute -bottom-1 -right-1 size-5 rounded-br-lg border-b-4 border-r-4 border-confere" />

                  {/* Instrução no topo da moldura */}
                  <div className="mt-4 flex justify-center">
                    <span className="rounded-full bg-black/60 px-3 py-1 text-xs font-semibold text-white/90 backdrop-blur-md">
                      Enquadre a nota fiscal aqui
                    </span>
                  </div>

                  {/* Linha guia de centro */}
                  <div className="mb-4 flex justify-center">
                    <span className="rounded-full bg-black/60 px-3 py-1 text-[0.6875rem] text-white/70 backdrop-blur-md">
                      Mantenha o documento reto e iluminado
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Modo de Preview da Foto Capturada */}
        {modo === 'preview' && (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3">
            <div className="relative max-h-[70vh] max-w-full overflow-hidden rounded-2xl border border-white/20 bg-black shadow-2xl">
              <img
                src={previewUrl}
                alt="Prévia do documento capturado"
                className="max-h-[70vh] w-auto object-contain"
              />
            </div>
            <p className="text-xs text-white/75">
              Certifique-se de que os números, CNPJ e valores estão nítidos antes de enviar.
            </p>
          </div>
        )}
      </main>

      {/* Barra de Ações Inferior */}
      <footer className="relative z-10 shrink-0 bg-black/80 px-4 py-4 backdrop-blur-md sm:px-6">
        {modo === 'camera' ? (
          <div className="flex items-center justify-between sm:justify-center sm:gap-12">
            {/* Fallback para abrir câmera nativa do celular ou arquivo */}
            <div className="w-24 text-left">
              <button
                type="button"
                onClick={() => inputNativoRef.current?.click()}
                className="flex flex-col items-center gap-1 text-xs font-semibold text-white/80 hover:text-white"
                title="Usar aplicativo de câmera nativo ou galeria"
              >
                <span className="grid size-10 place-items-center rounded-full bg-white/10 hover:bg-white/20">
                  <Icone nome="arquivo" className="size-5" />
                </span>
                <span>Galeria / App</span>
              </button>
            </div>

            {/* Botão de Disparo (Shutter Button) */}
            <div className="flex justify-center">
              <button
                type="button"
                onClick={capturarFoto}
                disabled={carregando || erroCamera}
                className="group relative flex size-18 items-center justify-center rounded-full border-4 border-white bg-white/20 p-1 shadow-lg transition active:scale-90 disabled:opacity-40"
                aria-label="Tirar foto do documento"
              >
                <span className="size-14 rounded-full bg-white transition group-hover:scale-95 group-active:scale-90" />
              </button>
            </div>

            {/* Espaçador equilibrado para manter o botão no centro */}
            <div className="w-24 text-right">
              <button
                type="button"
                onClick={fechar}
                className="text-xs font-semibold text-white/70 hover:text-white"
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          /* Ações do modo Preview */
          <div className="mx-auto flex max-w-md flex-col gap-2.5 sm:flex-row sm:justify-center">
            <button
              type="button"
              onClick={tirarOutra}
              disabled={enviando}
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-xl border border-white/30 bg-white/10 px-5 text-sm font-bold text-white transition hover:bg-white/20 active:scale-95 disabled:opacity-50"
            >
              <Icone nome="girar" className="size-4" />
              Tirar Outra
            </button>
            <button
              type="button"
              onClick={confirmarEnvio}
              disabled={enviando}
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-confere px-5 text-sm font-bold text-white shadow-lg transition hover:bg-[#2559e0] active:scale-95 disabled:opacity-50"
            >
              <Icone nome="check" className="size-4" />
              {enviando ? 'Enviando…' : 'Usar esta foto'}
            </button>
          </div>
        )}

        {/* Input file nativo invisível com capture="environment" */}
        <input
          ref={inputNativoRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={lidarComArquivoNativo}
        />
      </footer>
    </div>
  )
}
