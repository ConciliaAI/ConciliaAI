export default function EmMigracao({ titulo }) {
  return (
    <div className="grid gap-6">
      <h1 className="text-[2.125rem] font-extrabold">{titulo}</h1>
      <div className="grid justify-items-start gap-2 rounded-2xl border border-dashed border-borda bg-papel p-8">
        <p className="font-semibold">Esta tela ainda está sendo passada para o novo front.</p>
        <p className="text-sm text-apoio">
          Enquanto isso, ela funciona na versão atual da plataforma, em{' '}
          <a className="font-semibold text-tinta underline" href="http://localhost:8000" target="_blank" rel="noreferrer">localhost:8000</a>.
        </p>
      </div>
    </div>
  )
}
