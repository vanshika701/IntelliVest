export function FieldError({ id, message }: { id?: string; message: string | null | undefined }) {
  return message ? <p id={id} role="alert" className="mt-1 text-xs text-[var(--color-losses)]">{message}</p> : null
}
